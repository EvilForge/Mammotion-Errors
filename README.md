# Mammotion-Errors
An attempt to centralize the error codes you can get from the Mammotion line of lawn mower robots. (this first dump was formatted from me gathering info from the web manually, then formatted using chatgpt, so, i havent vetted it yet)

Programmatically or via the app, you can see the error description and code, but if youre into home automation (and its more likely that people owning a robor lawn more ARE into home automation, in my experience!), it would be nice to have a way to look up what an error number means.  

Its true that the manuals provide some of this information, but not everything. Your paper owners manual also does not get updated when they update the firmware... 

So, i'll start this by putting up some info i have gathered. I only have one model, however, so my error may not be exactly what another model uses (like the normal battery low error code 1005 may mean something more serious on other models..). Add more models as verified into the model string array.

I AM OPEN TO UPDATES!  I would love it if other owners can add or correct things.. also I really only speak english natively, and I'd mangle another translation I am certain, but I dont mind keeping other language files here.

I'll try to put them in a json style format, since I suspect its more useful to programmers, but even in JSON its not hard to read thru by a human and find information. 

Heres the fields:
1. Error Number - an integer (hopefully.. if they start putting alpha chars into error numbers.. it's ok.)
2. Severity - Info, Warning, Error, Debug. This is a bit subjective.
3. Model(s) - a list of models this might apply to.
4. Error Text - If Mammotion supplies a text string to go with it, put it here. IF the ERROR IS UNKNOWN, state as much: "UNKNOWN"

As far as different languages i think its bettter to separate them by file... 

NOTE - if you use the Home Assistant Plugin (https://github.com/mikey0000/Mammotion-HA) you can use the logbook or history to see your previously recorded errors and codes (add the last_error and last_error_code to the history chart to correlate them). If you pipe your HA info to Prometheus/VictoriaMetrics its possible to get a list of all the numbers using PromQL too..
