# Platsdatabas – källor och begränsningar

* **Kommuner (290)**: https://github.com/marcusasplund/kommundata, `Svenska_kommuner_2017.json`, MIT-licens. Kommunkoder, kommunnamn och ungefärliga kommunmittpunkter. Data från 2017.
* **Tätorter (2 017)**: https://github.com/hej2010/svenska-orter, `src/svenska-orter.json`, Apache License 2.0. Bearbetad SCB-tätortsdata (2020) med WGS84-koordinater. Upphov och licens tillhör respektive källa.

Koordinaterna är **representativa punkter**, inte en arbetsplatsadress eller en exakt kommungräns. Därför kan en kommuns mittpunkt inte bevisa att varje arbetsplats i kommunen ligger inom 30 km. Vid tvetydiga tätortsnamn utan kommunuppgift returnerar uppslaget ingen koordinat. Namngivna men olösta arbetsorter ska inte räknas som lokala.

Kör tester med `python -m unittest discover -s tests` från projektroten. Denna databas kräver ingen extern API-nyckel och gör inga nätverksanrop vid sökning.
