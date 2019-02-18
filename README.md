Nibe - An home assistant plugin to get data from Nibe Uplink
============================================================

Preparation
------------

Register an nibe uplink application on: https://api.nibeuplink.com/

  * Set the redirect url to match `<http or https>://<your_home_assistant_url_or_local_ip>:<port>/api/nibe/auth`
  * Take note of the **Identifer** (client_id) and the **Secret**

Installation
------------

 * Clone or copy the root of the repository into `<config dir>/custom_components`
 * Add a nibe configuration block to your `<config dir>/configuration.yaml` see example below

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

              # retrieve categories, leave empty for all, remove tag for none
              categories:
                - <identifer>  # category identifier like 'SYSTEM_1'
                - <identifer>

              # retrieve status parameters, remove tag for none
              statuses:

          # Optional list of additional parameters to retrieve, can be done here or on the sensor platform.
          sensors:
            - <parameter identifier>
            - <parameter identifier>

          # Optional list of switches (note, for ability to change, you need to use writeaccess and have payed license).
          switches:
            - hot_water_boost

          # Optional climate entities. Leave empty for all, remove tag for none.
          climates:

          # Optional water_heaters entities. Leave empty for all, remove tag for none.
          water_heaters:
```

Minimal configuration
```yaml
nibe
    systems:
        - system: <required system identifier>
          units:
            - unit: 0
              categories:
```

Optional explicit sensor setup
```yaml
sensor:
  - platform: nibe
    system   : <required system identifier>
    parameter: <required parameter identifier>
```

Optional explicit switch setup
```yaml
switch:
  - platform: switch
    system   : <required system identifier>
    parameter: <required parameter identifier>
```
