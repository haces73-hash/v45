import os,re,math,datetime,threading,time
from collections import defaultdict
from flask import Flask, jsonify, request, send_from_directory
import requests
app=Flask(__name__,static_folder='static')
# Prevent concurrent expensive searches from saturating the small Render instance.
_search_gate=threading.BoundedSemaphore(value=1)
CITIES={'Halmstad':(56.6745,12.8568),'Falkenberg':(56.9055,12.4912),'Varberg':(57.1056,12.2508),'Göteborg':(57.7089,11.9746),'Helsingborg':(56.0465,12.6945)}
TERMS=['anläggningsarbetare','markarbetare','byggarbetare','byggmedhjälpare','betongarbetare','snickare','träarbetare','snickeri','träindustri','produktionsmedarbetare','industriarbetare','verkstadsmedarbetare','montör','svetsare','metallarbetare']
# More entry-level construction titles, including common alternative spellings.
# These searches run first in both CV modes; no licence/senior filters are relaxed.
BUILD_TERMS=['anläggningsarbetare','markarbetare','byggarbetare','byggmedhjälpare',
             'betongarbetare','grovarbetare','byggnadsarbetare','byggmontör',
             'mark och anläggning','anläggningsmedarbetare','hjälparbetare bygg','bygg lärling','bygglärling','lärling anläggning','lärling snickare','byggservice','rivningsarbetare','mark och väg',
             'träarbetare bygg','byggnadsträarbetare','vägarbetare']
def search_terms(full_cv=False):
 return list(dict.fromkeys(BUILD_TERMS+TERMS+(FULL_CV_EXTRA_TERMS if full_cv else [])))
def match_counts(found):
 areas=['Bygg och anläggning','Snickeri och träproduktion','Industri och produktion','Svets och metallarbete']
 return {area:sum(j.get('cv_match_area')==area for j in found.values()) for area in areas}
FULL_CV_EXTRA_TERMS=['personlig assistent','omsorgsmedarbetare','vårdbiträde','butiksmedarbetare','butikssäljare','lagerarbetare','orderplockare','servicemedarbetare']
# Mandatory B/other road driving licences are disqualifying; forklift licences are separate.
ROAD_LICENSE=re.compile(r'(?i)(?<!truck)(?:\b(?:b|be|c|ce|d)[- ]?körkort\b|\bkörkort\b|\bkörbehörighet\b|\b(?:b|be|c|ce|d)[- ]?behörighet\b|\bdriving licen[cs]e\b|\bdriver.s licen[cs]e\b|\begen bil\b|\btillgång till bil\b)')
MANDATORY_WORDS=re.compile(r'(?i)\b(?:krav|krävs|måste|obligatorisk\w*|förutsättning|förutsätter|ska ha|skall ha|du har|innehar|erfordras|required|must have|necessary)\b')
OPTIONAL_WORDS=re.compile(r'(?i)\b(?:meriterande|önskvärt|önskas|fördel|plus|bonus|inte ett krav|inget krav|ej krav|not required|preferred)\b')
FORKLIFT=re.compile(r'(?i)\b(?:truckkort|truckbehörighet|truckförarbevis)\b')
NO_ROAD_LICENSE=re.compile(r'(?i)(?:inget|utan|ej|inte)\s+(?:\w+\s+){0,3}(?:körkort|b[- ]?körkort)\s+(?:krävs|behövs)|körkort\s+(?:krävs|behövs)\s+inte')
def _license_in(value):
 """Detect road licences only, never forklift certificates or mere field names."""
 if isinstance(value,str):return bool(ROAD_LICENSE.search(value))
 if isinstance(value,list):return any(_license_in(x) for x in value)
 if isinstance(value,dict):
  return any(_license_in(v) for k,v in value.items() if k not in
    ('required','mandatory','optional','meritorious','preferred','nice_to_have','must_have'))
 return False

def _structured_license_evidence(ad):
 """Return status and an anonymous field path; never mix preferred with required."""
 if ad.get('driving_license_required') is True:return ('required','driving_license_required')
 if ad.get('driving_license_required') is False:return ('not_required','driving_license_required')
 optional_path=''
 for root in ('must_have','required_qualifications','mandatory_qualifications'):
  value=ad.get(root)
  if _license_in(value):return ('required',root)
 for root in ('requirements','qualifications','driving_license','driving_licence','driving_licenses','licenses'):
  value=ad.get(root)
  if isinstance(value,dict):
   for key in ('must_have','mandatory','required'):
    item=value.get(key)
    if item is True and _license_in(value):return ('required',root+'.'+key)
    if item is not True and _license_in(item):return ('required',root+'.'+key)
   for key in ('nice_to_have','meritorious','optional','preferred'):
    if _license_in(value.get(key)):optional_path=root+'.'+key
   if value.get('required') is False and _license_in(value):optional_path=root+'.required=false'
  elif isinstance(value,list):
   for item in value:
    if not isinstance(item,dict) or not _license_in(item):continue
    flag=item.get('required',item.get('mandatory'))
    if flag is True:return ('required',root+'[].required=true')
    if flag is False:optional_path=root+'[].required=false'
 return ('optional',optional_path) if optional_path else (None,'')

def _explicit_optional_licence(text):
 """Only explicit meritorious wording near road-driving licence counts as a conflict."""
 for clause in re.split(r'[\n\r;.!?•]+',str(text or '')):
  if ROAD_LICENSE.search(clause) and (NO_ROAD_LICENSE.search(clause) or re.search(
   r'(?i)(?:körkort|driving licen[cs]e).{0,45}(?:meriterande|önskvärt|fördel|preferred|inte ett krav)|(?:meriterande|önskvärt|fördel|preferred).{0,45}(?:körkort|driving licen[cs]e)',clause)):
   return True
 return False

def _license_conflict(ad,title,text):
 structured,path=_structured_license_evidence(ad)
 if structured!='required':return False
 description=ad.get('description')
 texts=[text]
 if isinstance(description,dict):texts.extend(str(description.get(k) or '') for k in ('text','text_formatted'))
 elif isinstance(description,str):texts.append(description)
 return any(_explicit_optional_licence(x) for x in texts)

def _structured_license(ad):
 return _structured_license_evidence(ad)[0]

def _license_decision(ad,title,text):
 """Keep the decision trace without storing actual qualification values."""
 structured,path=_structured_license_evidence(ad)
 if structured=='required':return ('required','Obligatoriskt körkort enligt strukturerade krav','strukturerat obligatoriskt',path)
 # Explicit mandatory text must also be checked when structured metadata says not required.
 if structured=='not_required' and not re.search(r'(?i)(?:körkort|driving licen[cs]e).{0,55}(?:krävs|är ett krav|obligatoriskt|måste ha)|(?:krävs|krav på|måste ha|obligatoriskt).{0,55}(?:b[- ]?körkort|driving licen[cs]e)',str(text or '')):return ('not_required','Inget obligatoriskt körkort enligt annonsdata','strukturerat ej krav',path)
 extras=[]
 for key in ('requirements','qualifications','must_have','nice_to_have','license','driving_license'):
  value=ad.get(key)
  if isinstance(value,str):extras.append(value)
 desc=ad.get('description')
 if isinstance(desc,dict):
  for key in ('text','text_formatted','conditions'):
   if desc.get(key):extras.append(str(desc[key]))
 blob='\n'.join([str(title or ''),str(text or '')]+extras)
 optional=structured=='optional';forklift=bool(FORKLIFT.search(blob))
 for clause in re.split(r'[\n\r;.!?•]+',blob):
  if not ROAD_LICENSE.search(clause):continue
  if NO_ROAD_LICENSE.search(clause):optional=True;continue
  # Mandatory and preferred terms can coexist in a sentence. Avoid a false
  # positive if the licence itself is explicitly only meritorious.
  optional_near=bool(re.search(r'(?i)(?:körkort|driving licen[cs]e).{0,45}(?:meriterande|önskvärt|fördel|preferred)|(?:meriterande|önskvärt|fördel|preferred).{0,45}(?:körkort|driving licen[cs]e)',clause))
  if optional_near or OPTIONAL_WORDS.search(clause):optional=True;continue
  if MANDATORY_WORDS.search(clause):return ('required','Obligatoriskt körkort framgår av annonstexten','text uttryckligt krav','description/text')
  optional=True
 if optional:return ('optional','Körkort nämns men är inte bekräftat som obligatoriskt – kontrollera originalannonsen','meriterande eller ej styrkt krav',path or 'description/text')
 if forklift:return ('forklift','Truckkort nämns; kontrollera villkoren.','truckkort','description/text')
 return ('not_mentioned','Inget obligatoriskt B-körkort framgår av tillgänglig text – kontrollera originalannonsen','inget belagt körkortskrav','')


def employment_extent(ad):
 """Conservative full-time classification from structured JobSearch/JobAd Links fields."""
 fields=[]
 for key in ('working_hours_type','working_hours','employment_type','employment_extent',
             'extent','scope','work_time_extent','worktime_extent','work_time','working_time'):
  value=ad.get(key)
  if isinstance(value,dict):
   fields.extend(str(value.get(k) or '') for k in ('label','name','value','text','description'))
  elif isinstance(value,(str,int,float)):fields.append(str(value))
 for key in ('employment','conditions'):
  obj=ad.get(key)
  if isinstance(obj,dict):
   for k in ('working_hours_type','working_hours','extent','scope'):
    val=obj.get(k)
    if isinstance(val,dict):fields.extend(str(val.get(t) or '') for t in ('label','name','value'))
    elif isinstance(val,(str,int,float)):fields.append(str(val))
 blob=' '.join(fields).casefold()
 if re.search(r'\b(?:deltid|part.time|part time|timanställning|timvikarie|extraarbete|extrajobb|behovsanställning)\b',blob):return 'part_time'
 if re.search(r'\b(?:heltid|full.time|full time|100\s*procent)\b|100\s*%',blob):return 'full_time'
 # Use explicit hours only when the source actually supplies an extent.
 if re.search(r'\b(?:[1-9]|[1-3][0-9])\s*(?:timmar|hours)\s*(?:per|/)\s*(?:vecka|week)\b',blob):return 'part_time'
 return 'unknown'

def _enrichment_status(ad):
 return ad.get('detail_check_status','Ej kontrollerad')

def _deadline(ad):
 for v in (ad.get('application_deadline'),ad.get('application_deadline_date'),ad.get('last_application_date'),ad.get('deadline')):
  if isinstance(v,str) and v.strip():return v.strip()
 return ''

def _verification_state(text,status):
 if len((text or '').strip())<45:return 'unverified'
 return 'review' if status in ('unclear','not_mentioned','optional') else 'partial'

def license_classification(ad,title,text):
 status,explanation,_,_=_license_decision(ad,title,text)
 return status,explanation

# v30: Prefer structured workplace fields; never infer city from search location.
PLACEMENT=re.compile(r'(?im)\b(?:placeringsort|arbetsort|stationeringsort|arbetsplats(?:en)?\s*(?:ligger|finns)?\s*i)\s*[:–-]?\s*([A-Za-zÅÄÖåäö\- ]{2,45})')
PLACE_ALIASES={'halmstads kommun':'Halmstad','falkenbergs kommun':'Falkenberg','laholms kommun':'Laholm','hylte kommun':'Hylte','varbergs kommun':'Varberg','båstads kommun':'Båstad'}
def _place_name(value):
 if isinstance(value,dict):
  for key in ('label','name','municipality','city','value','name_sv'):
   name=_place_name(value.get(key))
   if name:return name
  return ''
 if isinstance(value,list):
  for item in value:
   name=_place_name(item)
   if name:return name
  return ''
 if not isinstance(value,str):return ''
 value=re.sub(r'\s+',' ',value).strip(' ,.;:-').casefold().split(',')[0].strip()
 value=PLACE_ALIASES.get(value,value)
 if value.casefold().endswith(' kommun'):value=value[:-7]
 return value.strip().title()
def _known_place(value):
 name=_place_name(value)
 return name if name.casefold() in MUNICIPALITY_CENTERS else ''
def workplace_from_text(text,metadata_city):
 for match in PLACEMENT.finditer(text or ''):
  place=match.group(1).splitlines()[0].strip()
  for key in sorted(MUNICIPALITY_CENTERS,key=len,reverse=True):
   if re.match(r'(?i)^'+re.escape(key)+r'\b',place):return key.title()
 return _known_place(metadata_city) or _place_name(metadata_city)
def _coordinates(*sources):
 for source in sources:
  if not isinstance(source,dict):continue
  candidates=[source]
  for key in ('coordinates','location','position','workplace_address','workplace','address'):
   nested=source.get(key)
   if isinstance(nested,dict):candidates.append(nested)
  for candidate in candidates:
   lat=candidate.get('latitude',candidate.get('lat'))
   lon=candidate.get('longitude',candidate.get('lon',candidate.get('lng')))
   try:
    lat=float(lat);lon=float(lon)
    if 54<=lat<=70 and 10<=lon<=25:return lat,lon
   except (TypeError,ValueError):pass
 return None,None
SCB_MUNICIPALITIES={'1380':'Halmstad','1382':'Falkenberg','1383':'Varberg','1381':'Laholm','1315':'Hylte','1384':'Kungsbacka','1278':'Båstad','1292':'Ängelholm','1283':'Helsingborg'}
def _municipality_value(value):
 if isinstance(value,dict):
  for key in ('label','name','name_sv','municipality','municipality_name','municipality_code','code','value'):
   result=_municipality_value(value.get(key))
   if result:return result
  return ''
 if isinstance(value,int) and not isinstance(value,bool):value=str(value)
 if isinstance(value,str) and value.strip() in SCB_MUNICIPALITIES:return SCB_MUNICIPALITIES[value.strip()]
 return _known_place(value)

def _workplace_places(entry):
 if not isinstance(entry,dict):return []
 values=[entry.get(k) for k in ('municipality','municipality_name','municipality_code','municipality_concept_id','city','locality','workplace_city')]
 for key in ('address','workplace_address','location'):
  nested=entry.get(key)
  if isinstance(nested,dict):
   values.extend(nested.get(k) for k in ('municipality','municipality_name','municipality_code','city','locality'))
 return values
def _location_options(ad,text=''):
 entries=[]
 for key in ('workplace_addresses','workplaces','locations'):
  val=ad.get(key)
  if isinstance(val,list):entries.extend(x for x in val if isinstance(x,dict))
 for key in ('workplace_address','workplace'):
  val=ad.get(key)
  if isinstance(val,dict):entries.append(val)
 if not entries:entries=[ad]
 options=[];seen=set()
 for entry in entries:
  lat,lon=_coordinates(entry)
  name=next((_municipality_value(v) for v in _workplace_places(entry) if _municipality_value(v)), '')
  if not name and entry is ad:
   name=next((_municipality_value(v) for v in _workplace_places(ad) if _municipality_value(v)), '')
  if not name and lat is None:continue
  signature=(name,lat,lon)
  if signature not in seen:
   seen.add(signature);options.append({'city':name,'lat':lat,'lon':lon})
 explicit=workplace_from_text(text,'') if text else ''
 if explicit and _place_coords(explicit):
  matches=[x for x in options if x['city'].casefold()==explicit.casefold()]
  options=matches or [{'city':explicit,'lat':None,'lon':None}]
 return options

def _city_from_ad(ad,addr,text):
 workplace=ad.get('workplace') or {}
 fields=_workplace_places(addr)+_workplace_places(workplace)+_workplace_places(ad)
 for key in ('workplace_addresses','workplaces','locations'):
  entries=ad.get(key)
  if isinstance(entries,list):
   for entry in entries:fields.extend(_workplace_places(entry))
 known=next((_municipality_value(v) for v in fields if _municipality_value(v)), '')
 fallback=next((_place_name(v) for v in fields if _place_name(v)), '')
 return workplace_from_text(text,known or fallback)

def dist(a,b,c,d):
 p1,p2=math.radians(a),math.radians(c);dp=math.radians(c-a);dl=math.radians(d-b)
 x=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
 return round(6371*2*math.atan2(math.sqrt(x),math.sqrt(1-x)),1)
def clean(s):return re.sub('<[^>]+>',' ',s or '').strip()

def application_route(ad, fallback_url='', external_source=False):
 """Only claim an external application when a specific application link is provided."""
 details=_as_dict(ad.get('application_details'))
 url=_first_str(details.get('url'),ad.get('application_url'),ad.get('apply_url'))
 email=_first_str(details.get('email'),ad.get('application_email'))
 info=_first_str(details.get('information'),ad.get('application_instructions'))
 if url.startswith('https://') or url.startswith('http://'):
  return {'type':'external','url':url,'email':'','note':'Annonsen anger en ansökningslänk. Följ instruktionerna på webbplatsen.'}
 if email and '@' in email:
  return {'type':'email','url':'','email':email,'note':'Annonsen anger en e-postadress för ansökan. Inget mejl skickas automatiskt.'}
 if external_source:
  return {'type':'check','url':fallback_url,'email':'','note':'Extern annons. Kontrollera ansökningssättet på originalwebbplatsen.'}
 return {'type':'check','url':fallback_url,'email':'','note':'Ansökningssättet kan inte bekräftas från annonsdata. Läs originalannonsen.'}

def parse_job(ad,source):
 title=ad.get('headline') or ad.get('title') or ''
 employer=ad.get('employer') or {}; addr=ad.get('workplace_address') or {}
 desc=ad.get('description') or {}
 if isinstance(desc,dict): desc=desc.get('text') or desc.get('text_formatted') or ''
 if not isinstance(employer,dict):employer={}
 if not isinstance(addr,dict):addr={}
 text=clean(desc)
 raw_city=_city_from_ad(ad,addr,'')
 actual_city=_city_from_ad(ad,addr,text)
 lic_state,lic_text=license_classification(ad,title,text)
 if lic_state=='required' and _license_conflict(ad,title,text):
  lic_state,lic_text='conflict','Motstridiga körkortsuppgifter – kontrollera originalannonsen'
 if lic_state=='required':return None
 options=_location_options(ad,text)
 lat,lon=_coordinates(addr,ad)
 if actual_city.casefold()!=raw_city.casefold():lat=lon=None
 if options:
  actual_city=options[0]['city'] or actual_city
  lat,lon=options[0]['lat'],options[0]['lon']
 url=ad.get('webpage_url') or ad.get('application_details',{}).get('url') or ''
 if not isinstance(url,str) or not url.startswith('https://'):url=''
 return {'id':str(ad.get('id') or url),'title':title,'company':employer.get('name') or 'Arbetsgivare ej angiven','city':actual_city, 'description':text[:8500], 'published':ad.get('publication_date') or '', 'deadline':_deadline(ad), 'url':url, 'lat':lat,'lon':lon,'location_options':options,'source':source,'license':lic_text,'license_status':lic_state,'verification_status':_verification_state(text,lic_state),'application':application_route(ad,url),'employment_extent':employment_extent(ad),'detail_check_status':'Fullständig annons från JobSearch' if len(text)>=45 else 'Väntar på detaljkontroll'}
# CV-baserade yrkesområden: byggutbildning, snickeri/produktion och svetsutbildning.
CV_GROUPS={
 'Bygg och anläggning':{'anläggningsarbetare':48,'markarbetare':47,'byggmedhjälpare':48,'betongarbetare':44,'grovarbetare':40,'byggarbetare':43,'byggnadsträarbetare':43,'träarbetare':42,'snickare':40,'byggmontör':38,'byggnadsarbetare':44,'anläggningsmedarbetare':44,'vägarbetare':38,'hjälparbetare':35,'bygglärling':42,'bygglärling':42,'rivningsarbetare':38,'byggservice':39,'lärling':32},
 'Snickeri och träproduktion':{'snickeri':45,'snickare':43,'träindustri':43,'träbearbetning':43,'träproduktion':43,'möbelsnickare':33,'sågverk':34},
 'Industri och produktion':{'produktionsmedarbetare':42,'industriarbetare':41,'produktionsarbetare':42,'verkstadsmedarbetare':42,'montör':40,'montagearbetare':41,'maskinoperatör':32,'produktionsoperatör':32},
 'Svets och metallarbete':{'metallarbetare':36,'svetsare':35,'svetsoperatör':35,'svetsmontör':35,'plåtbearbetare':34,'metallbearbetare':34}}
PRIORITY=('Bygg och anläggning','Snickeri och träproduktion','Industri och produktion','Svets och metallarbete')
FULL_CV_GROUPS={'Omsorg och personlig assistans':{'personlig assistent':36,'omsorgsmedarbetare':32,'vårdbiträde':30,'omsorgspersonal':30},'Lager och butik':{'lagerarbetare':34,'lagerpersonal':33,'orderplockare':30,'butiksmedarbetare':34,'butikssäljare':32},'Service':{'servicemedarbetare':29,'servicepersonal':28}}
FULL_PRIORITY=PRIORITY+tuple(FULL_CV_GROUPS)
EXCLUDED_OCCUPATIONS=re.compile(r'(?i)\b(?:lagerarbetare|lagerpersonal|lagerchef|truckförare|orderplockare|butiksmedarbetare|butikssäljare|kassapersonal|personlig assistent|vårdbiträde|undersköterska|sjuksköterska|omsorgspersonal|kundtjänst|servicemedarbetare|receptionist|säljare|butikschef|hemtjänst|vårdpersonal|lageroperatör)\b')
ELECTRICAL_SPECIALIST=re.compile(r'(?i)(?:elektronik|elektriker|elteknik|elinstallatör|automationstekniker|styrsystem|kretskort|pcb|lödning|elektrisk konstruktion)')
ELECTRICAL_MANDATORY=re.compile(r'(?i)(?:\\b(?:krav|krävs|måste|ska ha|skall ha|erfarenhet av|utbildning inom)\\b.{0,85}\\b(?:el|elektronik|elteknik|automation|lödning|kretskort)\\b|\\b(?:el|elektronik|elteknik|automation|lödning|kretskort)\\b.{0,85}\\b(?:krav|krävs|måste|utbildning|erfarenhet)\\b)')
def reject_reason(j,full_cv=False):
 if is_blocked_employer(j):return 'Veterankraft'
 title=(j.get('title') or '').casefold()
 desc=(j.get('description') or '')[:8500]
 if not full_cv and EXCLUDED_OCCUPATIONS.search(title):return 'Utanför vald CV-profil'
 if SENIOR_TITLE.search(title) or SENIOR_REQUIREMENTS.search(desc):return 'Seniorroll/erfarenhetskrav'
 if REQUIRED_CERTIFICATION.search(desc):return 'Obligatoriskt yrkescertifikat'
 if ELECTRICAL_SPECIALIST.search(title) or (ELECTRICAL_SPECIALIST.search(desc) and (ELECTRICAL_MANDATORY.search(desc) or re.search(r'(?i)(?:krav|krävs|måste|utbildning|erfarenhet).{0,90}(?:elektronik|elteknik|automation|lödning|kretskort)',desc))):
  return 'El-/elektronikspecialisering'
 if MANDATORY_EXPERIENCE.search(desc):return 'Obligatorisk längre erfarenhet'
 return None

REQUIRED_CERTIFICATION=re.compile(r'(?i)(?:\b(?:yrkesbevis|gesällbrev|svetslicens|svetscertifikat|certifierad svetsare)\b.{0,55}\b(?:krav|krävs|obligatorisk)|\b(?:krav på|måste ha|ska ha)\b.{0,55}\b(?:yrkesbevis|gesällbrev|svetslicens|svetscertifikat)\b)')
# Senior refers to experience/responsibility, not the applicant's age.
SENIOR_TITLE=re.compile(r"(?i)\b(?:senior|sr\.?|lead|principal|expert|specialist|arbetsledare|platschef|projektledare|projektchef|teamledare|produktionschef|byggchef|avdelningschef|enhetschef|konstruktör|civilingenjör|förman|site manager|supervisor|foreman)\b|(?:ledande|ansvarig)\s+(?:montör|snickare|byggarbetare|anläggningsarbetare)")
# Explicit senior-level requirements anywhere in the ad; do not reject all mentions
# of "senior" in unrelated company descriptions.
SENIOR_REQUIREMENTS=re.compile(r"(?i)(?:\b(?:vi söker|söker en|som|rollen som|tjänsten som|befattningen som|krav på|erfarenhet som)\s+(?:en\s+|ett\s+)?(?:senior|arbetsledare|platschef|projektledare|förman|teamledare)\b|\b(?:minst|minimum|lägst|åtminstone)\s*(?:[3-9]|1[0-9])\s*(?:\+\s*)?års?\s*(?:dokumenterad\s+|relevant\s+|praktisk\s+|yrkes)?erfarenhet\b|\b(?:[3-9]|1[0-9])\s*(?:\+\s*)?års?\s+erfarenhet\s+(?:krävs|är ett krav|av)\b|\b(?:flerårig|mångårig|gedigen)\s+(?:yrkes)?erfarenhet\s+(?:krävs|är ett krav)\b)")

MANDATORY_EXPERIENCE=re.compile(r'(?i)(?:minst|minimum|lägst)\s*[3-9]\s*års?\s*(?:erfarenhet|yrkeserfarenhet)|\b(?:yrkesbevis|gesällbrev)\s*(?:är\s*)?(?:ett\s*)?krav')
LICENSE_RISK=re.compile(r'(?i)(?:körkort|förarbevis|truckkort|certifikat)')
POSITIVE=re.compile(r'(?i)(?:junior|nybörjare|utan erfarenhet|ingen erfarenhet krävs|upplärning|introduktion|meriterande|praktiskt arbete)')
# Block known unsuitable recruiting provider regardless of role wording.
# Check both employer and recruiting brand in the listing URL; never reject
# unrelated ads merely because they mention the provider in a description.
BLOCKED_EMPLOYERS={'veterankraft'}
def is_blocked_employer(ad):
 if not isinstance(ad,dict):return False
 names=[ad.get('company'),ad.get('recruiter'),ad.get('recruiting_company')]
 from urllib.parse import urlsplit
 urls=[ad.get('url'),(ad.get('application') or {}).get('url')]
 for name in names:
  if isinstance(name,str) and any(blocked in re.sub(r'[^a-z0-9åäö]','',name.casefold()) for blocked in BLOCKED_EMPLOYERS):
   return True
 for url in urls:
  if not isinstance(url,str):continue
  try:
   hostname=(urlsplit(url).hostname or '').casefold()
   if hostname=='veterankraft.se' or hostname.endswith('.veterankraft.se'):return True
  except ValueError:pass
 return False

# Genomförda utbildningar och verifierade kompetenser enligt Kevins uppdaterade CV.
# Nyckelorden är endast positiva matchningssignaler, inte intyg om särskilda arbetsgivarkrav.
KEVIN_SKILLS={
 'Säkra lyft':r'(?i)säkra\s+lyft|säkert\s+lyft|lyftarbete',
 'Liftutbildning 1a/1b/3a/3b':r'(?i)liftutbildning|liftkort|mobila\s+arbetsplattformar|saxlift|bomlift',
 'Fallskydd':r'(?i)fallskydd',
 'APV / Arbete på väg':r'(?i)arbete\s+på\s+väg|\bapv\b|\bsbsv\b',
 'Damm och kvarts':r'(?i)kvartsdamm|kvarts|dammhantering',
 'Brandfarliga ämnen':r'(?i)brandfarliga\s+(?:ämnen|varor)',
 'Safe Construction Training':r'(?i)safe\s+construction|byggbranschens\s+säkerhetsutbildning',
 'HLR och L-ABC':r'(?i)\bhlr\b|\bl-abc\b|första\s+hjälpen',
 'MIG/MAG-svetsning':r'(?i)\bmig\b|\bmag\b|mig[/-]mag',
 'AutoCAD och ritningsarbete':r'(?i)autocad|cad.ritning|ritningsarbete',
 'Möbeltillverkning och snickeri':r'(?i)möbeltillverkning|möbelsnickeri|möbelproduktion',
 'Microsoft Office':r'(?i)microsoft\s+office|officepaketet',
 'Engelska':r'(?i)engelska|english',
}
def matching_skills(text):
 return [name for name,pattern in KEVIN_SKILLS.items() if re.search(pattern,text or '')]

def score_job(j,full_cv=False):
 if reject_reason(j,full_cv):return None
 title=(j.get('title') or '').casefold()
 desc=(j.get('description') or '')[:8500]
 groups=[]
 for group,words in (dict(CV_GROUPS,**FULL_CV_GROUPS) if full_cv else CV_GROUPS).items():
  strength=max((points for word,points in words.items() if word in title),default=0)
  if strength:groups.append((group,strength))
 if not groups:return None
 # Pick the most specific CV category; building is only first when the title
 # actually denotes a construction job rather than generic 'snickare'.
 explicit_build=re.search(r'(?i)(?:anläggning|markarbet|bygg|betong|grovarbet)',title)
 explicit_wood=re.search(r'(?i)(?:snickeri|snickare|träindustri|träbearbet|träproduktion|möbelsnickare|sågverk)',title)
 explicit_weld=re.search(r'(?i)(?:svets|metall|plåtbearbet)',title)
 if explicit_build and not explicit_wood: preferred='Bygg och anläggning'
 elif explicit_wood and not explicit_build: preferred='Snickeri och träproduktion'
 elif explicit_weld and not explicit_build: preferred='Svets och metallarbete'
 else:preferred=None
 if preferred and any(group==preferred for group,_ in groups):
  groups.sort(key=lambda x:(x[0]!=preferred,-x[1]))
 else:groups.sort(key=lambda x:((FULL_PRIORITY if full_cv else PRIORITY).index(x[0]),-x[1]))
 score=groups[0][1]
 if POSITIVE.search(desc):score+=6
 skills=matching_skills(desc)
 score+=min(12,3*len(skills))
 j['cv_skills_matched']=skills
 if MANDATORY_EXPERIENCE.search(desc):score-=28
 if j.get('license_status')=='unclear':score-=8
 if j.get('verification_status')=='unverified':score-=35
 elif j.get('verification_status')=='review':score-=6
 if j.get('km') is not None:score+=max(0,20-min(j['km'],100)*0.35)
 published=j.get('published') or ''
 try:
  date=datetime.date.fromisoformat(published[:10])
  score+=max(0,12-max(0,(datetime.date.today()-date).days)*0.5)
 except ValueError:pass
 if not desc:score-=15
 j['match_score']=round(score,1)
 # Show profession-specific skills first; general English/Office matches should not obscure them.
 professional=[x for x in skills if x not in ('Engelska','Microsoft Office')]
 j['match_reason']='CV-match: '+groups[0][0]+(' · relevanta yrkeskompetenser: '+', '.join(professional[:3]) if professional else '')+(' · kontrollera erfarenhetskrav' if MANDATORY_EXPERIENCE.search(desc) else '')
 j['cv_match_area']=groups[0][0]
 j['priority']=(FULL_PRIORITY if full_cv else PRIORITY).index(groups[0][0])+1
 return j


def _as_dict(value):
 return value if isinstance(value,dict) else {}
def _as_list(value):
 return value if isinstance(value,list) else []
def _first_str(*values):
 for value in values:
  if isinstance(value,str) and value.strip():return value.strip()
 return ''
def parse_external(ad):
 """Normalize JobAd Links entries; skip ads without a trustworthy original URL."""
 if not isinstance(ad,dict):return None
 links=_as_list(ad.get('source_links'))
 link=_as_dict(links[0]) if links else {}
 employer=_as_dict(ad.get('employer'))
 addr=_as_dict(ad.get('workplace_address'))
 title=_first_str(ad.get('headline'),ad.get('title'),ad.get('occupation_label'))
 description=ad.get('description')
 if isinstance(description,dict):description=_first_str(description.get('text'),description.get('text_formatted'))
 text=clean(description if isinstance(description,str) else '')
 url=_first_str(link.get('url'),link.get('source_url'),ad.get('url'),ad.get('webpage_url'))
 if not url.startswith('https://') or not title:return None
 lic_state,lic_text=license_classification(ad,title,text)
 if lic_state=='required' and _license_conflict(ad,title,text):
  lic_state,lic_text='conflict','Motstridiga körkortsuppgifter – kontrollera originalannonsen'
 if lic_state=='required':return None
 source=_first_str(link.get('label'),link.get('source'),ad.get('source')) or 'Extern jobbsajt via JobAd Links'
 options=_location_options(ad,text)
 latitude,longitude=_coordinates(addr,ad)
 city=_city_from_ad(ad,addr,'')
 actual_city=_city_from_ad(ad,addr,text)
 if actual_city.casefold()!=city.casefold():latitude=longitude=None
 city=actual_city
 if options:
  city=options[0]['city'] or city
  latitude,longitude=options[0]['lat'],options[0]['lon']
 return {
  'id':'links:'+str(ad.get('id') or url),
  'title':title,'company':_first_str(employer.get('name'),ad.get('employer_name')) or 'Arbetsgivare ej angiven',
  'city':workplace_from_text(text,city),'description':text[:8500],'published':_first_str(ad.get('publication_date'),ad.get('published')),
  'deadline':_deadline(ad),'url':url,
  'lat':latitude,'lon':longitude,'location_options':options,'source':source,
  'license':lic_text,'license_status':lic_state,'verification_status':_verification_state(text,lic_state),'application':application_route(ad,url,external_source=True),'employment_extent':employment_extent(ad),'detail_check_status':'Väntar på detaljkontroll'
 }
def _normalize_key(j):
 # Duplicate ads from multiple providers may have different IDs.
 # Prefer identical canonical destination; otherwise same title/employer/city.
 from urllib.parse import urlsplit,parse_qsl,urlunsplit,urlencode
 u=j.get('url') or ''
 if u:
  parts=urlsplit(u)
  if parts.netloc.lower().endswith('arbetsformedlingen.se'):
   return ('url',parts.path.rstrip('/').lower())
  query=urlencode(sorted((k,v) for k,v in parse_qsl(parts.query) if not k.lower().startswith(('utm_','fbclid','gclid'))))
  return ('url',parts.netloc.lower(),parts.path.rstrip('/').lower(),query)
 return ('job',j['title'].strip().casefold(),j['company'].strip().casefold(),j['city'].strip().casefold())
# Municipality centers for approximate distance only when a listing has no coordinates.
# A municipality-wide listing is marked approximate, never precise.
MUNICIPALITY_CENTERS={
 'halmstad':(56.6745,12.8568),'falkenberg':(56.9055,12.4912),
 'varberg':(57.1056,12.2508),'laholm':(56.5121,13.0437),
 'båstad':(56.4265,12.8538),'helsingborg':(56.0465,12.6945),
 'ängelholm':(56.2428,12.8622),'höganäs':(56.1997,12.5578),
 'klippan':(56.1355,13.1309),'åstorp':(56.1357,12.9451),
 'ö rkelljunga':(56.2833,13.2781),'örkelljunga':(56.2833,13.2781),
 'hylte':(56.9984,13.2385),'kungsbacka':(57.4872,12.0761),
 'markaryd':(56.4614,13.5978),'ljungby':(56.8340,13.9408),
 'hässleholm':(56.1590,13.7664),'göteborg':(57.7089,11.9746),
 'mölndal':(57.6559,12.0137),'ulricehamn':(57.7916,13.4142),
 'borås':(57.7210,12.9401),'våxtorp':(56.4225,13.1217)
}
def _place_coords(name):
 n=(name or '').strip().casefold()
 for key,coords in MUNICIPALITY_CENTERS.items():
  if n==key or n.startswith(key+' ') or n.endswith(' '+key):return coords
 return None
def _location_diagnosis(raw,parsed):
 """Diagnose original source fields without exposing the original address."""
 if not isinstance(raw,dict):return 'Ogiltigt API-objekt'
 addr=raw.get('workplace_address')
 if not isinstance(addr,dict):addr={}
 if parsed and parsed.get('lat') is not None and parsed.get('lon') is not None:return 'GPS finns'
 if parsed and _place_coords(parsed.get('city')):return 'Känd ort'
 fields=_workplace_places(addr)+[addr.get(k) for k in ('region','street_address')]
 fields.extend(_workplace_places(raw))
 workplace=raw.get('workplace')
 if isinstance(workplace,dict):fields.extend(_workplace_places(workplace))
 for key in ('workplace_addresses','workplaces','locations'):
  values=raw.get(key)
  if isinstance(values,list):
   for item in values:
    if isinstance(item,dict):fields.extend(_workplace_places(item)+[item.get('coordinates')])
 if not any(v is not None and v!='' for v in fields):return 'Kommun/ort saknas i API-svaret'
 if any(_place_name(v) for v in fields):return 'Ortnamn finns men känns inte igen'
 return 'Platsfält finns men kan inte tolkas'

# v35: expose only location field names and data types, never values.
_LOCATION_KEYS=('workplace_address','workplace_addresses','workplace','workplaces',
 'location','locations','position','coordinates','municipality','municipality_code',
 'municipality_concept_id','city','locality','region','county','latitude','longitude','lat','lon','lng')
def _location_shape(raw):
 if not isinstance(raw,dict):return {'format':'ogiltigt objekt','fält':{}}
 fields={}
 for key in _LOCATION_KEYS:
  if key not in raw:continue
  val=raw[key]
  if isinstance(val,dict):
   fields[key]={'typ':'objekt','underfält':sorted(str(k) for k in val)[:25]}
  elif isinstance(val,list):
   first=next((x for x in val if isinstance(x,dict)),None)
   fields[key]={'typ':'lista','underfält':sorted(str(k) for k in first)[:25] if first else []}
  else:fields[key]={'typ':type(val).__name__,'har_värde':val is not None and val!=''}
 return {'format':'platsfält' if fields else 'inga identifierade platsfält','fält':fields}
def _diagnostic_source(kind):
 return 'Platsbanken / JobSearch' if kind=='jobsearch' else 'JobAd Links / externa jobbsajter'

def _enrich_jobsearch_location(raw,parsed,diagnostics):
 if not parsed or parsed.get('lat') is not None or _place_coords(parsed.get('city')):return parsed
 title=(raw.get('headline') or raw.get('title') or '').casefold()
 if not any(w in title for w in ('bygg','anlägg','markarb','betong','snick','träarb','grovarb','rivning','vägarb','lärling','hjälparb')):return parsed
 ident=str(raw.get('id') or '')
 if not re.fullmatch(r'[A-Za-z0-9_-]{1,90}',ident):return parsed
 if ident in diagnostics['detail_attempt_ids'] or len(diagnostics['detail_attempt_ids'])>=6:return parsed
 diagnostics['detail_attempt_ids'].add(ident)
 try:
  r=requests.get('https://jobsearch.api.jobtechdev.se/ad/'+ident,timeout=5,headers={'Accept':'application/json','User-Agent':'Jobb4kevin/31'})
  r.raise_for_status()
  full=parse_job(r.json(),'Platsbanken / JobSearch')
  if full and (full.get('lat') is not None or _place_coords(full.get('city'))):
   parsed.update({key:full[key] for key in ('city','lat','lon','location_options')})
   diagnostics['detail_resolved_ids'].add(ident)
 except (requests.RequestException,ValueError,TypeError,KeyError):
  diagnostics['detail_failed_ids'].add(ident)
 return parsed

def _norm_match(value):
 return re.sub(r'[^a-zåäö0-9]+',' ',str(value or '').casefold()).strip()

def _linked_jobsearch_id(raw):
 """Only a source-provided Platsbanken ID or an explicit AF ad URL is trusted.
 JobAd Links' own ID is NOT assumed to be a JobSearch ID.
 """
 if not isinstance(raw,dict):return ''
 for key in ('jobsearch_id','platsbanken_id','arbetsformedlingen_id'):
  value=raw.get(key)
  if isinstance(value,(str,int)) and re.fullmatch(r'[0-9]{4,24}',str(value)):
   return str(value)
 links=_as_list(raw.get('source_links'))
 urls=[_as_dict(x).get('url','') for x in links]
 urls.extend([raw.get('url',''),raw.get('webpage_url','')])
 from urllib.parse import urlsplit
 for url in urls:
  if not isinstance(url,str):continue
  parsed=urlsplit(url)
  host=(parsed.hostname or '').lower()
  if host not in ('arbetsformedlingen.se','www.arbetsformedlingen.se','platsbanken.arbetsformedlingen.se'):continue
  match=re.search(r'/(?:annonser|annons|ad)/([0-9]{4,24})(?:/|$)',parsed.path)
  if match:return match.group(1)
 return ''

def _record_license_evidence(diagnostics,ad,title,text):
 status,_,kind,path=_license_decision(ad,title,text)
 if status=='required':
  diagnostics['license_evidence'][kind+' / '+(path or 'fält ej angivet')]+=1

def _confirm_from_source_id(raw,parsed,diagnostics):
 """Enrich from the canonical JobSearch detail API, using only a trusted ID."""
 if not parsed or parsed.get('verification_status')!='unverified':return parsed
 ident=_linked_jobsearch_id(raw)
 if not ident:
  diagnostics['source_id_missing']+=1
  parsed['detail_check_status']='Käll-ID saknas'
  return parsed
 if ident in diagnostics['source_id_attempted']:
  parsed['detail_check_status']='Väntar på detaljkontroll (dubblett)'
  return parsed
 if len(diagnostics['source_id_attempted'])>=20:
  parsed['detail_check_status']='Väntar på detaljkontroll (uppslagsgräns)'
  return parsed
 diagnostics['source_id_attempted'].add(ident)
 try:
  response=requests.get('https://jobsearch.api.jobtechdev.se/ad/'+ident,timeout=6,
   headers={'Accept':'application/json','User-Agent':'Jobb4kevin/39'})
  response.raise_for_status()
  detail=response.json()
  if not isinstance(detail,dict) or str(detail.get('id'))!=ident:
   diagnostics['source_id_mismatch']+=1
   parsed['detail_check_status']='Detaljkontroll: annan annons'
   return parsed
  # Verify identity BEFORE evaluating disqualifying requirements.
  raw_title=detail.get('headline') or detail.get('title') or ''
  raw_employer=detail.get('employer') or {}
  raw_company=raw_employer.get('name','') if isinstance(raw_employer,dict) else ''
  if _norm_match(raw_title)!=_norm_match(parsed.get('title')) or _norm_match(raw_company)!=_norm_match(parsed.get('company')):
   diagnostics['source_id_mismatch']+=1
   parsed['detail_check_status']='Detaljkontroll: annan annons'
   return parsed
  raw_description=detail.get('description') or {}
  raw_text=clean(raw_description.get('text','') if isinstance(raw_description,dict) else str(raw_description))
  if _license_conflict(detail,raw_title,raw_text):
   diagnostics['license_conflicts']+=1
   _,path=_structured_license_evidence(detail)
   diagnostics['license_block_rows'].append({'yrke':parsed.get('cv_match_area','Övrigt'),
      'beslut':'Behöver kontrolleras – motsägelse','fält':path or 'description/text',
      'grund':'Strukturerat krav motsägs av uttryckligen meriterande körkort i annonstext'})
   parsed['license_status']='conflict'
   parsed['license']='Motstridiga körkortsuppgifter – kontrollera originalannonsen'
   parsed['verification_status']='unverified'
   parsed['detail_check_status']='Motstridiga körkortsuppgifter'
   return parsed
  candidate=parse_job(detail,'Platsbanken / JobSearch')
  if not candidate:
   # A mandatory driving licence can make parse_job reject the ad.
   title=detail.get('headline') or detail.get('title') or ''
   description=detail.get('description') or {}
   text=clean(description.get('text','') if isinstance(description,dict) else str(description))
   status,_=license_classification(detail,title,text)
   if status=='required':
    diagnostics['source_id_license_rejected']+=1
    _record_license_evidence(diagnostics,detail,title,text)
    _,_,kind,path=_license_decision(detail,title,text)
    diagnostics['license_block_rows'].append({'yrke':parsed.get('cv_match_area','Övrigt'),
      'beslut':'Blockerad – obligatoriskt körkort','fält':path or 'description/text','grund':kind})
    return None
   return parsed
  if _norm_match(candidate.get('title'))!=_norm_match(parsed.get('title')) or _norm_match(candidate.get('company'))!=_norm_match(parsed.get('company')):
   diagnostics['source_id_mismatch']+=1
   parsed['detail_check_status']='Detaljkontroll: annan annons'
   return parsed
  if parsed.get('city') and candidate.get('city') and _norm_match(parsed['city'])!=_norm_match(candidate['city']):
   diagnostics['source_id_mismatch']+=1
   parsed['detail_check_status']='Detaljkontroll: annan annons'
   return parsed
  if candidate.get('license_status')=='required':
   diagnostics['source_id_license_rejected']+=1
   _record_license_evidence(diagnostics,detail,raw_title,candidate.get('description',''))
   _,_,kind,path=_license_decision(detail,raw_title,candidate.get('description',''))
   diagnostics['license_block_rows'].append({'yrke':parsed.get('cv_match_area','Övrigt'),
     'beslut':'Blockerad – obligatoriskt körkort','fält':path or 'description/text','grund':kind})
   return None
  for field in ('description','deadline','license','license_status','verification_status'):
   if candidate.get(field):parsed[field]=candidate[field]
  if candidate.get('application',{}).get('type') in ('email','external'):
   parsed['application']=candidate['application']
  if candidate.get('employment_extent')!='unknown':
   parsed['employment_extent']=candidate['employment_extent']
  parsed['detail_check_status']='Fullständig annons kontrollerad'
  diagnostics['source_id_completed']+=1
 except (requests.RequestException,ValueError,TypeError,KeyError):
  diagnostics['source_id_failed']+=1
  parsed['detail_check_status']='Detaljkontroll misslyckades'
 return parsed


def _fulltime_bucket(j,only_fulltime):
 if not only_fulltime:return None
 extent=j.get('employment_extent','unknown')
 if extent=='part_time':return 'exclude'
 # Unknown working hours are eligible for the top five when other requirements pass.
 # The card must still clearly say that hours have not been confirmed.
 return None

def _experience_evidence(text):
 """Show only requirements actually supported by the available advertisement."""
 if not text.strip():
  return ('unknown','Annonsbeskrivning saknas – erfarenhetskrav okända','Ingen annonstext tillgänglig')
 if re.search(r'(?i)\b(?:ingen erfarenhet krävs|utan tidigare erfarenhet|erfarenhet krävs inte)\b',text):
  return ('ok','Annonsen säger att tidigare erfarenhet inte krävs','Uttryckligt i annonstexten')
 for pattern in (r'(?i)\b(?:minst|minimum|lägst|cirka|ca)\s*(\d{1,2})\s*års?\s*(?:relevant\s+|praktisk\s+|yrkes)?erfarenhet',
                 r'(?i)\b(\d{1,2})\s*års?\s+(?:relevant\s+|praktisk\s+|yrkes)?erfarenhet\s+(?:krävs|är ett krav|efterfrågas)'):
  m=re.search(pattern,text)
  if m:
   years=int(m.group(1))
   return ('review',f'Annonsen nämner {years} års erfarenhet – uppfyllandet ej verifierat',f'Annonsens uttryckliga uppgift: {years} år. Kevins CV visar träutbildning, snickerierfarenhet och byggutbildning (Movant, 6 november 2026), men styrker inte automatiskt just detta krav.')
 # Only quote a bounded clause; avoid interpreting experience described as a benefit as a must-have.
 m=re.search(r'(?i)(?:erfarenhet av|erfarenhet från|erfarenhet inom|yrkesvana|yrkesbevis|gesällbrev|självständigt arbete)[^\n.!?]{0,105}',text)
 if m:
  excerpt=re.sub(r'\s+',' ',m.group(0)).strip()[:115]
  return ('review','Annonsen nämner: ”'+excerpt+'”','Jämför formuleringen med Kevins träutbildning, tidigare träproduktion och avslutad byggutbildning (Movant, 6 november 2026). Kravet är inte automatiskt uppfyllt.')
 return ('review','Inget konkret erfarenhetskrav hittades i tillgänglig annonstext','Kevin har träutbildning, erfarenhet av träproduktion och avslutad byggutbildning (Movant, 6 november 2026). Det bekräftar inte att eventuella oskrivna krav uppfylls.')

def _license_evidence(job,text):
 status=job.get('license_status') or 'not_mentioned'
 if status=='conflict':
  optional=_explicit_optional_licence(text)
  if optional:
   return ('review','Motstridigt: strukturerat API-fält anger obligatoriskt körkort, men annonstexten beskriver körkort som meriterande','API: obligatoriskt körkort. Annonstext: meriterande/önskvärt. Kontrollera originalannonsen; ingen automatisk godkänd match.')
  return ('review','Motstridiga körkortsuppgifter enligt datakällan – exakt motsägelse kan inte styrkas i den tillgängliga texten','Kontrollera originalannonsen. Appen ska inte gissa att körkort är meriterande.')
 if status=='required':return ('block','Obligatoriskt körkort enligt annonsuppgifter','Ett styrkt obligatoriskt vägkörkortskrav blockerar matchningen')
 if status=='not_required':return ('ok','API anger att körkort inte är obligatoriskt','Strukturerad uppgift; kontrollera alltid originalannonsen')
 if status=='optional':return ('review','Körkort är meriterande eller nämns utan bekräftat krav','Körkort som bara är meriterande blockerar inte')
 if status=='forklift':return ('review','Truckkort nämns – inte samma sak som B-körkort','Kontrollera om truckkort faktiskt är obligatoriskt')
 return ('review','Inget obligatoriskt B-körkort identifierat i tillgängliga uppgifter','Avsaknad av kravuppgift är inte bevis för att körkort inte krävs')

def _requirement_checks(job):
 """Show actual evidence and unresolved requirements separately."""
 if not isinstance(job,dict):return []
 text=str(job.get('description') or '')
 licence=_license_evidence(job,text)
 experience=_experience_evidence(text)
 extent=job.get('employment_extent','unknown')
 hours={'full_time':('ok','Heltid enligt annonsdata','Omfattning angiven som heltid'),
        'part_time':('block','Deltid enligt annonsdata','Bekräftad deltid sorteras bort'),
        'unknown':('unknown','Arbetstid anges inte säkert','Kontrollera originalannonsen')}.get(extent,('unknown','Arbetstid okänd',''))
 application=job.get('application') or {}
 application_status=('ok','Ansökningsadress eller länk finns','Annonsdata anger ansökningssätt') if application.get('type') in ('email','external') and (application.get('email') or application.get('url')) else ('review','Ansökningssätt behöver kontrolleras','Öppna originalannonsen')
 description=('ok','Annonsbeskrivning tillgänglig','Text finns i sökresultatet') if len(text.strip())>=45 else ('unknown','Fullständig annonsbeskrivning saknas','Otillräckligt underlag för kravbedömning')
 city=job.get('city') or ''
 place=('review',f'Arbetsort enligt annonsdata: {city} – exakt arbetsplats och avstånd ej verifierade','Avstånd kan vara missvisande när annonsen bara anger kommun eller en övergripande ort') if city else ('unknown','Arbetsort saknas – avstånd okänt','Kan inte räkna säkert avstånd')
 return [dict(name=name,status=value[0],message=value[1],evidence=value[2]) for name,value in (
   ('Körkort',licence),('Erfarenhet',experience),('Arbetstid',hours),
   ('Arbetsort',place),('Ansökan',application_status),('Annonsunderlag',description))]

def _attach_requirement_checks(items):
 for item in items:item['requirement_checks']=_requirement_checks(item)
 return items

def _classify_listing(j):
 """Separate verified candidates from ads requiring manual checks."""
 if not j:return None
 if j.get('license_status')=='required':return 'rejected'
 if j.get('verification_status')=='unverified':return 'needs_review'
 if j.get('license_status') in ('not_mentioned','unclear','conflict','optional','forklift'):return 'needs_review'
 if j.get('verification_status')=='review':return 'needs_review'
 if j.get('employment_extent')=='unknown':return 'needs_review'
 return 'qualified'

def _add_candidate(ad,found,city,radius,full_cv=False,diagnostics=None):
 if not ad or not ad.get('id'):return
 if diagnostics is not None:
  diagnostics['seen_ids'].add(str(ad['id']))
  diagnostics['source_seen'][ad.get('_origin','Källa okänd')].add(str(ad['id']))
  if is_blocked_employer(ad):diagnostics['rejected']['Veterankraft'].add(str(ad['id']))
 if is_blocked_employer(ad):return
 if radius and ad.get('location_options'):
  eligible=[];known=[]
  for option in ad['location_options']:
   coords=(option['lat'],option['lon']) if option['lat'] is not None and option['lon'] is not None else _place_coords(option['city'])
   if coords:
    km=dist(*CITIES[city],*coords);known.append(km)
    if km<=radius:eligible.append((km,option))
  if eligible:
   _,selected=min(eligible,key=lambda x:x[0]);ad['city'],ad['lat'],ad['lon']=selected['city'],selected['lat'],selected['lon']
  elif known:
   if diagnostics is not None:diagnostics['rejected']['Utanför sökradien'].add(str(ad['id']))
   return
 if radius:
  approx=ad['lat'] is None
  coords=(ad['lat'],ad['lon']) if not approx else _place_coords(ad.get('city'))
  if coords is None:
   if diagnostics is not None:
    diagnostics['rejected']['Okänd plats'].add(str(ad['id']))
    diagnostics['unknown_by_source'][ad.get('_origin','Källa okänd')].add(str(ad['id']))
    diagnostics['unknown_reasons'][ad.get('_location_diagnosis','Orsak ej klassificerad')].add(str(ad['id']))
   return
  km=dist(*CITIES[city],*coords)
  ad['distance_approximate']=approx
  if km>radius:
   if diagnostics is not None:diagnostics['rejected']['Utanför sökradien'].add(str(ad['id']))
   return
  ad['km']=km
 else:
  coords=(ad['lat'],ad['lon']) if ad['lat'] is not None else _place_coords(ad.get('city'))
  ad['km']=dist(*CITIES[city],*coords) if coords else None
  ad['distance_approximate']=ad['lat'] is None
 reason=reject_reason(ad,full_cv)
 if reason and diagnostics is not None:diagnostics['rejected'][reason].add(str(ad['id']))
 ranked=score_job(ad,full_cv=full_cv)
 if not ranked:
  if diagnostics is not None and not reason:diagnostics['rejected']['Ingen CV-match'].add(str(ad['id']))
  return
 key=_normalize_key(ranked)
 current=found.get(key)
 if current is None or (-ranked['priority'],ranked['match_score'],len(ranked['description']))>(-current['priority'],current['match_score'],len(current['description'])):
  found[key]=ranked

# Regional coverage: municipalities used for checking and representative local queries.
HALLAND={'halmstad','laholm','falkenberg','varberg','kungsbacka','hylte'}
SOUTHERN_COUNTIES={
 'Halland':HALLAND,
 'Skåne':{'malmö','lund','helsingborg','ängelholm','båstad','höganäs','klippan','åstorp','örkelljunga','hässleholm','kristianstad','ystad','trelleborg','landskrona','eslöv','höör','svedala','staffanstorp','höganäs','simrishamn','osby','perstorp','hörby','sjöbo','skurup','burlöv','lomma','vellinge','svalöv','bjuv','åhus','tomelilla','broby','östra göinge','åstorp'},
 'Blekinge':{'karlskrona','karlshamn','ronneby','sölvesborg','olofström'},
 'Kronoberg':{'växjö','ljungby','älmhult','markaryd','tingsryd','alvesta','uppvidinge','lessebo'},
 'Kalmar':{'kalmar','nybro','oskarshamn','västervik','mönsterås','mörbylånga','borgholm','hultsfred','vimmerby','emmaboda','torsås','högsby'},
 'Jönköping':{'jönköping','värnamo','vetlanda','nässjö','eksjö','tranås','sävsjö','gislaved','gnosjö','habо','habo','mullsjö','vaggeryd','aneby'},
 'Västra Götaland':{'göteborg','mölndal','härryda','partille','borås','ulricehamn','mark','svenljunga','tranemo','alingsås','lerum','kungälv','stenungsund','trollhättan','vänersborg','uddevalla','skövde','lidköping','falköping','mariestad','lysekil','orust','tjörn','strö mstad','strömstad','tanum','var a','vara'}
}
SOUTHERN=set().union(*SOUTHERN_COUNTIES.values())
REGION_TOWNS={
 'halland':['Halmstad','Falkenberg','Varberg','Laholm','Kungsbacka','Hylte'],
 'south':['Halmstad','Helsingborg','Malmö','Lund','Kristianstad','Växjö','Jönköping','Kalmar','Karlskrona','Göteborg','Borås','Varberg']
}
def _region_accept(ad,region):
 if not ad:return False
 place=(ad.get('city') or '').strip().casefold()
 allowed=HALLAND if region=='halland' else SOUTHERN
 return place in allowed or any(place.startswith(name+' ') for name in allowed)
def _add_region_candidate(ad,found,region,full_cv=False,diagnostics=None):
 if ad and ad.get('location_options'):
  for option in ad['location_options']:
   candidate=dict(ad,city=option['city'],lat=option['lat'],lon=option['lon'])
   if _region_accept(candidate,region):ad=candidate;break
 if not _region_accept(ad,region):return
 # For regions, distance from Halmstad is information, not a radius filter.
 _add_candidate(ad,found,'Halmstad',0,full_cv=full_cv,diagnostics=diagnostics)

@app.get('/')
def index():return send_from_directory('static','index.html')
@app.get('/api/jobs')
def jobs():
 if not _search_gate.acquire(blocking=False):
  return jsonify(error='En jobbsökning pågår redan. Försök igen om en stund.',errors=['Sökning pågår']),503
 try:
  return _jobs_impl()
 finally:
  _search_gate.release()

def _jobs_impl():
 import time
 started_at=time.monotonic()
 full_cv=request.args.get('profile','priority').lower()=='full'
 only_fulltime=request.args.get('fulltime','1')!='0'
 region=request.args.get('region','radius').lower()
 region=region if region in ('radius','halland','south') else 'radius'
 city=request.args.get('city','Halmstad');city=city if city in CITIES else 'Halmstad'
 try:radius=int(request.args.get('radius','30'))
 except ValueError:radius=30
 radius=radius if radius in (0,10,30,50,100) else 30
 from collections import defaultdict
 found={};unknown_places={};unknown_stats=defaultdict(int);errors=[];sources_ok=set();external_candidates={}
 diagnostics={'license_conflicts':0,'license_block_rows':[],'license_evidence':defaultdict(int),'enrichment_by_category':defaultdict(lambda:{'attempted':0,'completed':0,'license_rejected':0}),'fulltime_excluded':set(),'fulltime_unknown':set(),'source_id_attempted':set(),'source_id_missing':0,'source_id_completed':0,'source_id_failed':0,'source_id_mismatch':0,'source_id_license_rejected':0,'location_samples':defaultdict(dict),'seen_ids':set(),'rejected':defaultdict(set),'missing_license':0,'source_seen':defaultdict(set),'unknown_by_source':defaultdict(set),'detail_attempt_ids':set(),'detail_resolved_ids':set(),'detail_failed_ids':set(),'unknown_reasons':defaultdict(set)}
 def record_sample(raw,parsed,source):
  if parsed and (parsed.get('lat') is not None or _place_coords(parsed.get('city'))):return
  shape=_location_shape(raw)
  reason=_location_diagnosis(raw,parsed)
  key=repr(shape)
  bucket=diagnostics['location_samples'][source]
  if key not in bucket and len(bucket)<4:
   bucket[key]={'diagnos':reason,'format':shape}
 def add_jobsearch(raw,region_name=None):
  parsed=parse_job(raw,'Platsbanken / JobSearch')
  record_sample(raw,parsed,'Platsbanken / JobSearch')
  if parsed:
   parsed['_origin']=_diagnostic_source('jobsearch')
   parsed['_location_diagnosis']=_location_diagnosis(raw,parsed)
  add_parsed(_enrich_jobsearch_location(raw,parsed,diagnostics),region_name)
 def add_external(raw):
  parsed=parse_external(raw)
  record_sample(raw,parsed,'JobAd Links / externa jobbsajter')
  if parsed:
   parsed['_origin']=_diagnostic_source('external')
   parsed['_location_diagnosis']=_location_diagnosis(raw,parsed)
  # First apply location/CV/senior filters. Enrich only after ALL searches,
  # globally ordered by actual CV priority (not API return order).
  if parsed:
   add_parsed(parsed)
   key=_normalize_key(parsed)
   if key in found and found[key].get('id')==parsed.get('id'):
    external_candidates[key]=raw
 def enrich_globally():
  eligible=[(key,found[key],raw) for key,raw in external_candidates.items()
            if key in found and found[key].get('verification_status')=='unverified']
  eligible.sort(key=lambda item:(item[1]['priority'],-item[1]['match_score'],
    item[1]['km'] if item[1]['km'] is not None else 9999,str(item[1]['id'])))
  for key,ad,raw in eligible[:6]:
   area=ad.get('cv_match_area','Övriga')
   before=len(diagnostics['source_id_attempted'])
   done=diagnostics['source_id_completed']
   rejected=diagnostics['source_id_license_rejected']
   checked=_confirm_from_source_id(raw,ad,diagnostics)
   stats=diagnostics['enrichment_by_category'][area]
   stats['attempted']+=len(diagnostics['source_id_attempted'])-before
   stats['completed']+=diagnostics['source_id_completed']-done
   stats['license_rejected']+=diagnostics['source_id_license_rejected']-rejected
   if checked is None:
    found.pop(key,None)
   else:
    # Re-evaluate CV and experience filters after obtaining the full ad.
    if not score_job(checked,full_cv=full_cv):
     found.pop(key,None)
    else:found[key]=checked
 def named_workplace(ad):
  # A generic or missing city must not hide a concrete city in the title.
  city_value=str(ad.get('city') or '').strip()
  title=str(ad.get('title') or '')
  far=('skellefteå','karlskrona','umeå','luleå','piteå','sundsvall','östersund','gävle','uppsala','stockholm','västerås','örebro','linköping','norrköping','jönköping','kalmar','växjö','kristianstad','malmö','lund','trelleborg','ystad')
  names=tuple(MUNICIPALITY_CENTERS)+far
  for name in sorted(set(names),key=len,reverse=True):
   if re.search(r'(?i)(?<!\w)'+re.escape(name)+r'(?!\w)',title):
    return name.title()
  if city_value.casefold() not in ('','okänd','okänt','okänd plats','ej angiven','saknas'):
   return city_value
  return ''
 def workplace_distance_state(ad):
  place=named_workplace(ad)
  if not place:return 'missing',''
  coords=_place_coords(place)
  if coords:
   km=dist(CITIES[city][0],CITIES[city][1],coords[0],coords[1])
   return ('outside' if radius and km>radius else 'inside'),place
  far=('skellefteå','karlskrona','umeå','luleå','piteå','sundsvall','östersund','gävle','uppsala','stockholm','västerås','örebro','linköping','norrköping','jönköping','kalmar','växjö','kristianstad','malmö','lund','trelleborg','ystad')
  if any(re.search(r'(?i)(?<!\w)'+re.escape(name)+r'(?!\w)',place) for name in far):
   return 'outside',place
  return 'unrecognized',place
 def collect_unknown(ad):
  if not ad or not ad.get('id'):return
  place_state,place_name=workplace_distance_state(ad)
  if place_state=='outside':
   unknown_stats['kand_ort_utanfor_omradet']+=1
   return
  if place_state=='inside':return
  if place_state=='unrecognized':
   unknown_stats['ortnamn_ej_igenkant']+=1
   return
  if ad.get('license_status')=='required':
   unknown_stats['korkortskrav']+=1
   return
  if is_blocked_employer(ad):return
  if only_fulltime and ad.get('employment_extent')=='part_time':return
  if ad.get('lat') is not None and ad.get('lon') is not None:return
  if _place_coords(ad.get('city')):return
  unknown_stats['plats_ej_bekraftad']+=1
  if any((option.get('lat') is not None and option.get('lon') is not None) or _place_coords(option.get('city')) for option in (ad.get('location_options') or [])):
   unknown_stats['annan_kand_plats']+=1
   return
  candidate=dict(ad)
  if not score_job(candidate,full_cv=full_cv):
   unknown_stats['ej_cv_match']+=1
   return
  candidate['km']=None
  candidate['review_bucket']='unknown_location'
  candidate['location_reason']=ad.get('_location_diagnosis') or 'Platsuppgift saknas'
  candidate['location_note']='Arbetsort ej bekräftad. Avståndet till Halmstad är okänt.'
  unknown_places[_normalize_key(candidate)]=candidate
  unknown_stats['cv_relevanta']+=1
 def add_parsed(ad,region_name=None):
  if ad is None:
   diagnostics['missing_license']+=1
   return
  if region_name:_add_region_candidate(ad,found,region_name,full_cv=full_cv,diagnostics=diagnostics)
  else:
   if radius:collect_unknown(ad)
   _add_candidate(ad,found,city,radius,full_cv=full_cv,diagnostics=diagnostics)
 def summary():
  return {'unknown_review_counts':dict(unknown_stats),'granskade_unika_annonser':len(diagnostics['seen_ids']),
          'uteslutna_per_orsak':{k:len(v) for k,v in diagnostics['rejected'].items()},
          'korkortskrav_vid_inlasning':diagnostics['missing_license'],
          'kvalificerade_unika':len(found),
          'heltid_bortsorterade':len(diagnostics['fulltime_excluded']),
          'omfattning_okand_granskning':len(diagnostics['fulltime_unknown']),
          'detaljuppslag_per_yrke':dict(diagnostics['enrichment_by_category']),
          'kall_id_saknas':diagnostics['source_id_missing'],
          'kall_id_uppslag':len(diagnostics['source_id_attempted']),
          'kall_id_kompletterade':diagnostics['source_id_completed'],
          'kall_id_korkort_blockerade':diagnostics['source_id_license_rejected'],
          'korkort_blockering_bevis':dict(diagnostics['license_evidence']),
          'korkort_motsagelser':diagnostics['license_conflicts'],
          'korkort_kontrollrader':diagnostics['license_block_rows'][:20],
          'kall_id_fel':diagnostics['source_id_failed'],
          'kall_id_mismatch':diagnostics['source_id_mismatch'],
          'granskade_per_kalla':{k:len(v) for k,v in diagnostics['source_seen'].items()},
          'okand_plats_per_kalla':{k:len(v) for k,v in diagnostics['unknown_by_source'].items()},
          'detaljer_forsok':len(diagnostics['detail_attempt_ids']),
          'detaljer_plats_hittad':len(diagnostics['detail_resolved_ids']),
          'detaljer_misslyckades':len(diagnostics['detail_failed_ids']),
          'okand_plats_orsaker':{k:len(v) for k,v in diagnostics['unknown_reasons'].items()},
          'platsfalt_exempel_per_kalla':{k:list(v.values()) for k,v in diagnostics['location_samples'].items()},
          'obs':'Antal avser API-annonser som granskats. En annons kan förekomma i flera sökningar och avslagsorsaker; totalsummor kan därför skilja sig.'}

 if region!='radius':
  # Run a bounded number of municipality-specific queries concurrently.
  # Region matching is based on the municipality field, not keyword mentions.
  from concurrent.futures import ThreadPoolExecutor,as_completed
  query_terms=search_terms(full_cv)
  towns=REGION_TOWNS[region]
  def search_local(pair):
   term,town=pair
   response=requests.get('https://jobsearch.api.jobtechdev.se/search',params={'q':term+' '+town,'limit':60},timeout=9,headers={'Accept':'application/json','User-Agent':'NoMoreClown/1.0'})
   response.raise_for_status()
   return response.json().get('hits',[])
  with ThreadPoolExecutor(max_workers=8) as pool:
   futures=[pool.submit(search_local,(term,town)) for town in towns[:6] for term in query_terms[:16]]
   for future in as_completed(futures):
    try:
     ads=future.result()
     sources_ok.add('Platsbanken / JobSearch')
     for ad in ads:add_jobsearch(ad,region)
    except (requests.RequestException,ValueError,KeyError,TypeError) as e:
     if len(errors)<8:errors.append('JobSearch: '+str(e)[:110])
  ranked=sorted(found.values(),key=lambda j:(j['priority'],-j['match_score'],j['km'] if j['km'] is not None else 9999,j['id']))
  for item in ranked:
   ft=_fulltime_bucket(item,only_fulltime)
   if ft=='exclude':
    diagnostics['fulltime_excluded'].add(str(item['id']))
    item['review_bucket']='excluded'
   else:
    if only_fulltime and item.get('employment_extent')=='unknown':
     diagnostics['fulltime_unknown'].add(str(item['id']))
    item['review_bucket']=_classify_listing(item)
  qualified=[j for j in ranked if j['review_bucket']=='qualified']
  needs_review=[j for j in ranked if j['review_bucket']=='needs_review']
  result=qualified[:80]
  search_seconds=round(time.monotonic()-started_at,1)
  return jsonify({'jobs':_attach_requirement_checks(result),'needs_review':_attach_requirement_checks(needs_review[:80]),'unknown_location':_attach_requirement_checks(unknown_ranked),'search_seconds':search_seconds,'fulltime_only':only_fulltime,'match_counts':match_counts(found),'diagnostics':summary(),'region':region,'source':', '.join(sorted(sources_ok)) or 'Inga källor nåddes','sources':sorted(sources_ok),'errors':errors,'note':'Körkorts- och seniorfilter: obligatoriska körkort och tydliga seniorroller utesluts. Halland omfattar sex kommuner. Södra Sverige omfattar här Halland, Skåne, Blekinge, Kronoberg, Kalmar, Jönköping och Västra Götaland. Jobbsökningarna görs via representativa orter; alla kommuner söks inte individuellt. Högst fem visas i appen.'})
 from concurrent.futures import ThreadPoolExecutor,as_completed
 terms=search_terms(full_cv)
 def fetch_query(task):
  kind,term,variant=task
  if kind=='jobsearch':
   params={'q':term+((' '+city) if variant=='city' else ''),'limit':100}
   if variant=='radius' and radius:
    params.update({'position':f"{CITIES[city][0]},{CITIES[city][1]}",'position.radius':radius})
   url='https://jobsearch.api.jobtechdev.se/search'
   timeout=6
  else:
   params={'q':term,'limit':40,'sort':'relevance'}
   url='https://links.api.jobtechdev.se/joblinks'
   timeout=4
  response=requests.get(url,params=params,timeout=timeout,headers={'Accept':'application/json','User-Agent':'Jobb4kevin/81'})
  response.raise_for_status()
  payload=response.json()
  if kind=='jobsearch':hits=payload.get('hits',[])
  else:hits=payload.get('hits',payload.get('joblinks',payload.get('results',[]))) if isinstance(payload,dict) else payload
  if not isinstance(hits,list):raise ValueError('Oväntat svarformat')
  return kind,hits
 tasks=[]
 for term in terms:
  tasks.append(('jobsearch',term,'radius' if radius else 'city'))
  if term in BUILD_TERMS and radius:tasks.append(('jobsearch',term,'city'))
  tasks.append(('links',term,''))
 with ThreadPoolExecutor(max_workers=6) as pool:
  futures=[pool.submit(fetch_query,task) for task in tasks]
  for future in as_completed(futures):
   try:
    kind,hits=future.result()
    if kind=='jobsearch':
     sources_ok.add('Platsbanken / JobSearch')
     for ad in hits:add_jobsearch(ad)
    else:
     sources_ok.add('JobAd Links / externa jobbsajter')
     for ad in hits:
      if isinstance(ad,dict):add_external(ad)
   except (requests.RequestException,ValueError,KeyError,TypeError) as e:
    if len(errors)<8:errors.append('Sökkälla: '+str(e)[:110])

 enrich_globally()
 ranked=sorted(found.values(),key=lambda j:(j['priority'],-j['match_score'],j['km'] if j['km'] is not None else 9999,j['id']))
 for item in ranked:
  ft=_fulltime_bucket(item,only_fulltime)
  if ft=='exclude':
   diagnostics['fulltime_excluded'].add(str(item['id']))
   item['review_bucket']='excluded'
  else:
   if only_fulltime and item.get('employment_extent')=='unknown':
    diagnostics['fulltime_unknown'].add(str(item['id']))
   item['review_bucket']=_classify_listing(item)
 qualified=[j for j in ranked if j['review_bucket']=='qualified']
 needs_review=[j for j in ranked if j['review_bucket']=='needs_review']
 result=qualified[:80]
 unknown_ranked=sorted((v for k,v in unknown_places.items() if k not in found),key=lambda j:(j['priority'],-j['match_score'],str(j['id'])))[:5]
 diagnostics['unknown_review_counts']=dict(unknown_stats)
 diagnostics['unknown_review_counts']['visas']=len(unknown_ranked)
 search_seconds=round(time.monotonic()-started_at,1)
 return jsonify({'jobs':_attach_requirement_checks(result),'needs_review':_attach_requirement_checks(needs_review[:80]),'unknown_location':_attach_requirement_checks(unknown_ranked),'search_seconds':search_seconds,'fulltime_only':only_fulltime,'match_counts':match_counts(found),'diagnostics':summary(),'source':', '.join(sorted(sources_ok)) or 'Inga källor nåddes','sources':sorted(sources_ok),'city':city,'radius':radius,'errors':errors[:8], 'note':'Körkortsfilter: obligatoriskt bilkörkort utesluts; meriterande truckkort kan tillåtas. Externa annonser kan ha förkortad text och måste dubbelkollas. JobSearch och JobAd Links används. Annonser utan GPS kan tas med när kommunen är känd; avståndet är då ungefärligt. Externa annonser kan ha förkortade beskrivningar. Kontrollera körkort och andra krav i originalannonsen.'})

# Explicit document endpoints: PDFs preview in the browser; DOCX downloads as real files.
@app.get('/documents/<kind>/<format>')
def documents(kind, format):
 files = {
  ('cv','pdf'):('Kevin_Martini_CV.pdf','application/pdf',False),
  ('cv','word'):('Kevin_Martini_CV.docx','application/vnd.openxmlformats-officedocument.wordprocessingml.document',True),
  ('brev','pdf'):('Kevins_personliga_brev.pdf','application/pdf',False),
  ('brev','word'):('Kevins_personliga_brev.docx','application/vnd.openxmlformats-officedocument.wordprocessingml.document',True),
 }
 item=files.get((kind,format))
 if not item:return jsonify(error='Dokumentet finns inte'),404
 name,mime,download=item
 return send_from_directory(app.static_folder,name,mimetype=mime,as_attachment=download,download_name=name,conditional=False)

@app.get('/health')
def health():
 # Liveness must never contact external job APIs or wait for the search lock.
 return jsonify(status='ok')
if __name__=='__main__':app.run(host='0.0.0.0',port=int(os.getenv('PORT','5000')))

@app.after_request
def _v50_no_cache(response):
 if response.mimetype in ('text/html','application/json') or request.path.startswith('/static/') or request.path.startswith('/documents/'):
  response.headers['Cache-Control']='no-store, no-cache, must-revalidate, max-age=0'
  response.headers['Pragma']='no-cache'
  response.headers['Expires']='0'
 return response
