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
 * Add a nibe configuration block to your `<config dir>/configuration.yaml` see example below

```bash
cd .homeassistant
mkdir custom_components
cd custom_components
git clone https://github.com/elupus/hass_nibe.git nibe
```

Configuration
-------------

Configuration description
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
```

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
