# Troubleshooting the Storage Tools Server

## Local Server Issues

### ZeroConf isn't working

* Make sure the Multicast DNS port (5353) is not being filtered by your network.
* Check the console logs to see which IP adresses `setup_zeroconf` is using.

## Back End Doesn't start

Error:

```sh
storage_tools_server_backend | psycopg2.OperationalError: connection to server at “localhost” (::1), port 5432 failed: Connection refused
storage_tools_server_backend | Is the server running on that host and accepting TCP/IP connections?
storage_tools_server_backend | connection to server at “localhost” (127.0.0.1), port 5432 failed: Connection refused
storage_tools_server_backend | Is the server running on that host and accepting TCP/IP connections?
```

The Back End was unable to connect to the database.  Verify that the database server is running
