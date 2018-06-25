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

Base configuration
```yaml
nibe:
    client_id: <client id from nibe uplink>
    client_secret: <client secret from nibe uplink>
    redirect_uri: <the redirect url you have entered at nibe uplink configuration>
    writeaccess: false # set to true to support climate write (needs new tokens)

    systems:
        - system: <required system identifier>
          categories: # optional list of categories to retrieve, leave empty for all, remove tag for none
            - <category identifer>

          statuses:   # optional list of status screens to retrieve, leave empty for all, remove tag for none
            - <status identifier>

          parameters: # optional list of additional parameters to retrieve, can be done here or on the sensor platform
            - <parameter identifier>
            - <parameter identifier>

```

Optional explicit climate system setup
```yaml
climate:
  - platform: nibe
    name: 'Climate System 1'
    system : <required system identifier>
    current: <parameter id of current temperature>
    target : <parameter id of target temperature>
    adjust : <parameter id of the parallel adjustment>
```

Optional explicit climate system setup with standard id's (climate value should be one of '1h', ..., '8h', '1c', ..., '8c')
```yaml
climate:
  - platform: nibe
    system : <required system identifier>
    climate: <required climate identifier as per above>
```

Optional explicit sensor setup
```yaml
sensor:
  - platform: nibe
    system   : <required system identifier>
    parameter: <required parameter identifier>
```
