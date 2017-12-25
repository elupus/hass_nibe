Nibe - An home assistant plugin to get data from Nibe Uplink
============================================================

Installation
------------

Make sure you have a nibe uplink account and you have registered an application on: https://api.nibeuplink.com/

Clone or copy the root of the repository into `<config dir>/custom_components`

Add a nibe configuration block to your `<config dir>/configuration.yaml`

Install nibeuplink module (currently not available PyPi)
`pip install git+https://github.com/elupus/nibeuplink.git`

```yaml
nibe:
    client_id: <client id from nibe uplink>
    client_secret: <client secret from nibe uplink>
    redirect_uri: <the redirect url you have entered at nibe uplink configuration>

    systems:
        - system: <required system identifier>
          writeaccess: false # set to true to support climate write (needs new tokens)
          categories: # optional list of categories to retrieve, leave empty for all
            - <category identifer>

          statuses:   # optional list of status screens to retrieve, leave empty for all
            - <status identifier>

          parameters: # optional list of additional parameters to retrieve, can be done here or on the sensor platform
            - <parameter identifier>
            - <parameter identifier>


climate: # optional climate system setup
  - platform: nibe
    name: 'Climate System 1'
    system : <required system identifier>
    current: 40033 # parameter id of current temperature
    target : 47398 # parameter id of target temperature
    adjust : 47011 # parameter id of the parallell adjustment

sensor: # optional explicit sensor
  - platform: nibe
    system: <required system identifier>
    parameter: <required parameter identifier>
```
