Jobb4kevin v59 – rättning av 500 Internal Server Error vid originaldokument.

Orsak: after_request använde response.path, som saknas i Flask Response. Nu används request.path.
Original-CV och personligt brev samt övriga funktioner är oförändrade.
