Nibe - An home assistant plugin to get data from Nibe Uplink
============================================================

Preparation
------------

Register an nibe uplink application on: https://api.nibeuplink.com/

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

 * If you are using windows, download the zip and extract the folder inside to your custom_components folder.
 * Rename the folder "hass_nibe-master" to "nibe" so that all the files should end up inside the a "nibe" under the custom_components folder.

  https://github.com/runevad/hass_nibe/blob/master/docs/nibe_files_windows.png


 * Add a nibe configuration block to your `<config dir>/configuration.yaml` see example below

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

* Go to the Configuration tab of Home Assistant

<img src="https://github.com/runevad/hass_nibe/blob/master/docs/configuration.png" alt="Configuration page" />

* Go to the Integration page
* Scroll all the way down (custom components end up last in the list)

<img src="https://github.com/runevad/hass_nibe/blob/master/docs/integrations.png" alt="Integrations page" />

* Enter the Nibe configuration
- Enter your **Callback url**, your **Identifer** (client_id) and the **Secret**
The configurator should send you to a page that has generated an access token.

<img src="https://github.com/runevad/hass_nibe/blob/master/docs/Nibe_config.png" alt="Nibe configurator" />

* Copy the code segment, go back to your other window or tab containing the Nibe configurator.
* Paste the code into the field that is displayed.

The system should now display your Nibe instance.

<img src="https://github.com/runevad/hass_nibe/blob/master/docs/Nibe_integration.png" alt="Integration page" />
<img src="https://github.com/runevad/hass_nibe/blob/master/docs/Nibe_integration_2.png" alt="Integration page 2" />

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
