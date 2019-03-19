Nibe - An home assistant plugin to get data from Nibe Uplink
============================================================

Preparation
------------

  * Register an nibe uplink application on: https://api.nibeuplink.com/
  * Set the redirect url to match `<http or https>://<your_home_assistant_url_or_local_ip>:<port>/api/nibe/auth`
  * Take note of the **Identifer** (client_id) and the **Secret**

Installation
------------

  * Clone or copy the root of the repository into `<config dir>/custom_components/nibe`

```bash
cd .homeassistant
mkdir custom_components
cd custom_components
git clone https://github.com/elupus/hass_nibe.git nibe
```

  If you are using Windows:
  * Download the zip file and extract the folder inside to your custom_components folder.
  * Rename the folder "hass_nibe-master" to "nibe".
    * *All files, including the .translation folder, should be inside the "nibe" catalog under the custom_components folder.*
  <img src="/docs/nibe_files_windows.png" alt="Windows folder" />


  * Add an empty nibe configuration block to your `<config dir>/configuration.yaml`
```yaml
nibe:
```
  * Restart your Home Assistant
    * *A notification error message should appear in Home Assistant after the first restart. This contains your system identifier info which is needed later for [Configuration](README.md#configuration)*

  * Go to the Integrations page located in Home Assistants Configuration dashboard
  * Scroll all the way down (custom components end up last in the list)
  <img src="/docs/integrations.png" alt="Integrations page" />

  * Click the Nibe Uplink configure button
  * Enter your **Callback url**, your **Identifer** (client_id) and the **Secret**
  <img src="/docs/nibe_config.png" alt="Configure uplink parameters" />

  * The configurator should send you to a authorization page that has generated a long access token.
  * Copy the long **code segment** and go back to your other window or tab containing the Nibe configurator.
  * Paste the long code into the field that is displayed, click Submit.
  <img src="/docs/nibe_authorize.png" alt="Authorize home assistant for nibe" />

  The system should now have access to the Nibe Uplink API.

  * Add some more info to your [Configuration](README.md#configuration)
```yaml
  nibe:
      systems:
          - system: <required system identifier>
            units:
              - unit: 0
            climates: True
            water_heaters: True
```
  * Restart your Home assistant again
    * *The integration page should then display all available entities.* 
  <img src="/docs/nibe_integration.png" alt="Integration page example" />

Configuration
-------------

Minimal configuration
```yaml
nibe:
    systems:
        - system: <required system identifier>
          units:
            - unit: 0
          climates: True
          water_heaters: True
```

Full configuration description
```yaml
nibe:
    systems:
        # required system identifier
        - system: <identifier>

          # list of units to retrieve data for
          units:
              # unit to retrieve data for (0 is the master unit and should always exist)
            - unit: <identifier>

              # Optional load of status entities
              categories: True

              # Optional load of status entities
              statuses: True

          # Optional list of additional parameters to retrieve, can be done here or on the sensor platform.
          sensors:
            - <parameter identifier>
            - <parameter identifier>

          # Optional list of switches (note, for ability to change, you need to use writeaccess and have payed license).
          switches:
            - hot_water_boost

          # Optional load climate entities
          climates: True

          # Optional load water_heaters entities
          water_heaters: True

          # Optional smart thermostats.
          thermostats:
            # Key in dict is external identifer in nibe uplink, it should
            # be an unique integer for this thermostat
            1:
              # Required friendly name of thermostat
              name: "Kitchen Thermostat"

              # Optional name of a home assistant entity representing current temperature
              current_temperature: input_number.current

              # Optional name of a home assistant entity representing valve position of
              # a thermostat. At the moment it's use case is unknown.
              # valve_position: input_number.valve

              # List of systems that this thermostat is affecting. This is
              # this is the sub climate system/area index (System 1, System 2, ..)
              # that the pump is controlling.
              systems: 1

            2:
              name: "Livingroom Thermostat"
              current_temperature: input_number.current
              systems: 1
```
