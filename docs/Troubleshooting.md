# Troubleshooting the Storage Tools Server

## Local Server Issues

## Dashbaord isn't connecting to local Server

* Verify
  * Verify that the server is by looking at the console output.
  * Verify that Devices can connect to the Server via the Device Dashboard-> Connection tab

* Restart
  * Try restarting the server with the `local_up.sh` script.
  * If that does not resolve the issue, remove local authentication in `config.local.yaml` by setting `use_local_auth` to `false`.  Only do this on networks that you trust.

## Device isn't connecting

Make sure the API Key Token for the device is in the server's keychain.  This can be done by either adding the Device's key to the Server's keychain, or setting the Device's key to an existing (or generated) key.

* Add the Device's key to the Server's keychain
  * Find the IP address for the Device, and go to http://ip_address:8811/ and select the "Config" tab.
  * Look for the value in "API Key Token" and copy it to the clipboard
  * On the Server dashboard, go to "Configure" -> "Keys"
  * Locate the "Insert Key" button
  * Set the name of the device in the "Paste Key Name" field
  * Set the key to the value in the clipboard
  * On the Device dashboard, go to "Connection" and press "Restart Connections"
* Set the Device's key to an existing or generated key
  * See [Key Management](KeyManagement.md) for details.

### ZeroConf isn't working

* Make sure the Multicast DNS port (5353) is not being filtered by your network.
* Check the console logs to see which IP adresses `setup_zeroconf` is using.

### The console is reporting "write() before start_response"

If you see this error message on the console:

```python
Error on request:
Traceback (most recent call last):
  File "/usr/local/lib/python3.12/site-packages/werkzeug/serving.py", line 370, in run_wsgi
    execute(self.server.app)
  File "/usr/local/lib/python3.12/site-packages/werkzeug/serving.py", line 336, in execute
    write(b"")
  File "/usr/local/lib/python3.12/site-packages/werkzeug/serving.py", line 261, in write
    assert status_set is not None, "write() before start_response"
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
```

You can safely ignore it. This message is caused by a user reloading the dashboard.

## Back End Doesn't start

Error:

```sh
storage_tools_server_backend | psycopg2.OperationalError: connection to server at “localhost” (::1), port 5432 failed: Connection refused
storage_tools_server_backend | Is the server running on that host and accepting TCP/IP connections?
storage_tools_server_backend | connection to server at “localhost” (127.0.0.1), port 5432 failed: Connection refused
storage_tools_server_backend | Is the server running on that host and accepting TCP/IP connections?
```

The Back End was unable to connect to the database.  Verify that the database server is running
