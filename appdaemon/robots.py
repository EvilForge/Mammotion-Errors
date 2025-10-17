import hassapi as hass
from datetime import datetime, timedelta, timezone
from typing import List, Dict
import math
import json
import os

class robotalert(hass.Hass):
    """
    Monitors a robot mower error code sensor and notifies configured notify targets. His name is 'garth'.
    YAML settings expected (example in apps.yaml):
      error_notify:
        - entity: notify.my_office_speak
      info_notify:
        - entity: notify.my_office_speak
      device: lawn_mower.garth
      battery: sensor.garth_battery
      progress: sensor.garth_progress
      charge_status: binary_sensor.garth_charging
      friendly_name: "Garth mower"
      error: sensor.garth_last_error_code
      error_text: sensor.garth_last_error
    """

    CODE_DESCRIPTIONS: Dict[str, str] = {}
    CODE_SEVERITIES: Dict[str, str] = {}

    @classmethod
    def load_code_descriptions(cls):
        json_path = os.path.join(os.path.dirname(__file__), "mammotion-errors-en.json")
        if not os.path.exists(json_path):
            # fallback: try absolute path
            json_path = "/appdaemon/config/apps/mammotion-errors-en.json"
        try:
            with open(json_path, "r") as f:
                data = json.load(f)
            cls.CODE_DESCRIPTIONS = {str(item["code"]): item["text"] for item in data if "code" in item and "text" in item}
            cls.CODE_SEVERITIES = {str(item["code"]): item.get("severity", "ERROR") for item in data if "code" in item}
        except Exception as e:
            print(f"Failed to load code descriptions: {e}")

    def initialize(self):
        # Load code descriptions and severities once at startup
        if not robotalert.CODE_DESCRIPTIONS:
            robotalert.load_code_descriptions()
        self.error_notify = [e.get("entity") if isinstance(e, dict) else e for e in self.args.get("error_notify", [])]
        self.info_notify = [e.get("entity") if isinstance(e, dict) else e for e in self.args.get("info_notify", [])]
        self.device = self.args.get("device")
        self.battery_entity = self.args.get("battery")
        self.progress_entity = self.args.get("progress")
        self.charge_status_entity = self.args.get("charge_status")
        self.friendly_name = self.args.get("friendly_name", self.device or "Robot")
        self.error_entity = self.args.get("error")
        self.error_text_entity = self.args.get("error_text")
        self.error_date_entity = self.args.get("error_date")
        if not self.error_entity:
            self.log("robotstatus: no 'error' entity configured; disabling.", level="WARNING")
            return

        # Listen for changes to the error code sensor
        self.listen_state(self._on_error_change, self.error_entity)

        # Optionally log initial state
        current = self.get_state(self.error_entity)
        if current and current not in ("none", "None", "", "0"):
            self.log(f"robotstatus: initial error state {current}; processing once on startup")
            # fire once to report any existing error on startup
            severity = self.CODE_SEVERITIES.get(current, self.CODE_SEVERITIES.get(str(current).lstrip('0'), "ERROR"))
            if severity.upper() == "IGNORE":
                self.log(f"{self.friendly_name}: Ignoring error code {current} (severity=IGNORE)")
                return
            
    def _on_error_change(self, entity, attribute, old, new, kwargs):
        # Only act on transitions into a non-empty/new code
        if new is None:
            return
        new_s = str(new).strip()
        if new_s in ("", "none", "None", "0"):
            self.log(f"{self.friendly_name}: error cleared (was: {old})")
            return
        if new_s == str(old):
            return
        # Use severity from JSON
        severity = self.CODE_SEVERITIES.get(new_s, self.CODE_SEVERITIES.get(str(new_s).lstrip('0'), "ERROR")).upper()
        if severity == "IGNORE":
            self.log(f"{self.friendly_name}: Ignoring error code {new_s} (severity=IGNORE)")
            return

        # If an error date entity is configured, skip if the reported error is older than 1 hour
        if self.error_date_entity:
            try:
                err_date_raw = self.get_state(self.error_date_entity)
                if err_date_raw not in (None, "", "None", "none"):
                    try:
                        err_dt = datetime.fromisoformat(str(err_date_raw))
                    except Exception:
                        try:
                            err_dt = datetime.fromtimestamp(float(err_date_raw))
                        except Exception:
                            err_dt = None

                    if err_dt is not None:
                        mytime = datetime.now(timezone.utc) - err_dt
                        if datetime.now(timezone.utc) - err_dt > timedelta(hours=1):
                            self.log(f"{self.friendly_name}: Ignoring error code {new_s} (reported at {err_dt} > 1 hour old mytime {mytime})")
                            return
            except Exception as e:
                self.log(f"{self.friendly_name}: could not evaluate error_date '{self.error_date_entity}': {e}", level="WARNING")

        self._handle_error_state(new_s)

    def _handle_error_state(self, code: str):
        code_str = str(code).lstrip("0") if str(code).isdigit() else str(code)
        code_key = code if code in self.CODE_DESCRIPTIONS else code_str if code_str in self.CODE_DESCRIPTIONS else code

        desc = self.CODE_DESCRIPTIONS.get(code_key, "Unknown error")
        severity = self.CODE_SEVERITIES.get(code_key, "ERROR").upper()
        err_text = self.safe_get(self.error_text_entity)
        battery = self.safe_get(self.battery_entity)
        progress = self.safe_get(self.progress_entity)
        charge = self.safe_get(self.charge_status_entity)

        msg_parts = [f"{severity} for {self.friendly_name}."]
        if desc:
            msg_parts.append(f"- {desc}.")
        # if err_text:
        #     msg_parts.append(f"Details: {err_text}")
        if battery is not None:
            msg_parts.append(f"Battery is {battery}%")
        if progress is not None:
            msg_parts.append(f"Task is {progress}% complete.")
        if charge is not None:
            msg_parts.append(f"Charging is {charge}")

        message = " | ".join(msg_parts)
        shortmessage = f"{severity}. {self.friendly_name} reported {desc}"

        # Decide notify targets by severity
        if severity == "INFO":
            targets = self.info_notify
            self.log(f"{self.friendly_name}: {severity.lower()}-level ({code}) -> notifying {targets}")
        else:
            targets = self.error_notify
            self.log(f"{self.friendly_name}: error-level ({code}) -> notifying {targets}", level="ERROR")

        if not targets:
            self.log("No notify targets configured; message: " + message, level="WARNING")
            return

        self._send_notifications(targets, message, shortmessage)

    def _send_notifications(self, notify_entities: List[str], message: str, shortmessage: str):
        for n in notify_entities:
            if not n:
                continue
            # convert 'notify.NAME' -> 'notify/NAME' service path for call_service
            service = n.replace(".", "/")
            if "pushover" in service:
                # Pushover expects title and message
                title = f"{self.friendly_name} Garth Alert"
                try:
                    self.log(f"Calling pushover notify service {service} with title: {title} and message: {shortmessage}")
                    self.call_service(
                        "notify/pushover",
                        service_data={
                            "title": title,
                            "message": shortmessage
                        },
                        # other kwargs also will be included in service_data
                    )
                except Exception as e:
                    self.log(f"Failed to call pushover notify service {service}: {e}", level="ERROR")
                continue
            else:
                try:
                    # AppDaemon call_service expects service path like 'notify/target'
                    self.log(f"Calling notify service {service} with message: {message}")
                    self.call_service(
                        "notify/send_message",
                        service_data={
                            "message": "speak",
                            "entity_id": n
                        },
                        # other kwargs also will be included in service_data
                        message=message
                    )
                    #self.call_service(service, message=message)
                except Exception as e:
                    self.log(f"Failed to call notify service {service}: {e}", level="ERROR")

    def safe_get(self, entity_id):
        if not entity_id:
            return None
        try:
            v = self.get_state(entity_id)
            return None if v in (None, "None", "none", "") else v
        except Exception:
            return None
# ...existing code...

class notifytest(hass.Hass):
    """Class to test media notify for alexa."""
    def initialize(self):
        required_args = [
            "device", "alexa_notify"
        ]
        missing_args = [arg for arg in required_args if arg not in self.args]
        if missing_args:
            self.log(f"Initialization Error. Missing config values: {missing_args}", level="WARNING")
            return
        device = self.args.get("device")
        if device:
            self.log(f"Initializing callback for {device}", level="INFO")
            self.listen_state(self.on_value_change, device)
        else:
            self.log(f"Error initializing sensor: {device}", level="ERROR")

    def on_value_change(self, entity, attribute, old, new, kwargs):
        name = self.args.get("friendly_name")
        message = f"{name} is now {new}."
        self.log(f"New State: {message}")
        # if state is paused, and 1 <= progress <= 99, then it (was?) stopped mid task. Stuck?  It isnt stuck if its non working hours, however.. 
        # if state is unknown.. hmm.. 
        # if state is paused and not charging and battery gets below 20% is it sitting idle slowly killing its battery?
        # self.notify(message, title="HA/APPD Restarted.", name="notify.alexa_media_my_office")
        for entry in self.args["alexa_notify"]:
            ntarget = entry["entity"]
            # self.log(f"ROBOTS,valuechange,notify {message} to service {ntarget}", level="INFO")
            # self.notify(message, title="{device} error.", name=service)
            self.call_service(
                "notify/send_message",
                service_data={
                    "message": "speak",
                    "entity_id": ntarget
                },
                # other kwargs also will be included in service_data
                message="<say-as interpret-as='interjection'>uh oh.</say-as> <audio src='soundbank://soundlibrary/musical/amzn_sfx_bell_short_chime_01'/> This is the new notify call using internal integrations."
            )
# be reallly careful here, i dont use this anymore cause it got stuck in a loop and generated >2000 events in HA within seconds..
class gpsoffset(hass.Hass):
    """Class to correct GPS satellite offset in google maps"""
    def initialize(self):
        required_args = [
            "device"
        ]
        missing_args = [arg for arg in required_args if arg not in self.args]
        if missing_args:
            self.log(f"Initialization Error. Missing config values: {missing_args}", level="WARNING")
            return
        device_tracker = self.args.get("device")
        if device_tracker:
            self.log(f"Initializing callback for {device_tracker}", level="INFO")
            self.listen_state(self.device_tracker_updated, device_tracker, attribute="latitude")
            self.listen_state(self.device_tracker_updated, device_tracker, attribute="longitude")
        else:
            self.log(f"Error initializing sensor: {device_tracker}", level="ERROR")

    def device_tracker_updated(self, entity, attribute, old, new, kwargs):
        # Get entity state and attributes
        device_tracker = self.args.get("device")
        device_data = self.get_state(device_tracker, attribute="all")

        # Extract latitude and longitude
        latitude = device_data["attributes"].get("latitude", "Unknown")
        longitude = device_data["attributes"].get("longitude", "Unknown")

        self.log(f"{device_tracker} is at ({latitude}, {longitude})")
        lat_offset = -0.1
        lon_offset = -0.1

        lat = latitude + ( lat_offset / 111320 )
        lon = longitude + ( lon_offset / (111320 * math.cos( lat * ( math.pi / 180 ))))

        self.set_state(device_tracker, state="home", attributes={"latitude": lat, "longitude": lon})
        self.log(f"Updated {device_tracker} to ({lat}, {lon})")
