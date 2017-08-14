Nibe - An home assistant plugin to get data from Nibe Uplink
============================================================

Installation
------------

Clone or copy the root of the repository into `<config dir>/custom_components`

Add a nibe configuration block to your `<config dir>/configuration.yaml`

```yaml
nibe:
    client_id: <client id from nibe uplink>
    client_secret: <client secret from nibe uplink>
    redirect_uri: <the redirect url you have entered at nibe uplink configuration>

```