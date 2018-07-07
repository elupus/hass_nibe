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
    client_id: <client id from nibe uplink>
    client_secret: <client secret from nibe uplink>
    redirect_uri: <the redirect url you have entered at nibe uplink configuration>
    writeaccess: false # set to true to support climate write (needs new tokens)

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

              # optional list of additional parameters to retrieve, can be done here or on the sensor platform
              sensors:
                - <parameter identifier>
                - <parameter identifier>

              # optional list of switches (note, for ability to change, you need to use writeaccess and have payed license)
              switches:
                - hot_water_boost

```

Minimal configuration
```yaml
    client_id: <client id from nibe uplink>
    client_secret: <client secret from nibe uplink>
    redirect_uri: <the redirect url you have entered at nibe uplink configuration>
    writeaccess: false # set to true to support climate write (needs new tokens)

    systems:
        - system: <required system identifier>
          units:
            - unit: 0
              categories:
```


Optional climate system setup with standard id's. climate field should be in the format of
`[1-4](h|c)(a?)` as an example `1h` for system 1 heating, `2ca` for system 2 cooling flow adjust
```yaml
climate:
  - platform: nibe
    system : <required system identifier>
    climate: <required climate identifier as per above>
```

Optional explicit climate system setup with fixed id
```yaml
climate:
  - platform: nibe
    name: 'Climate System 1'
    system : <required system identifier>
    current: <parameter id of current temperature>
    target : <parameter id of target temperature>
    adjust : <parameter id of the parallel adjustment, leave out if target should be updated>
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
