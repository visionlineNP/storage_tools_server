# Troubleshooting the Storage Tools Server

## Local Server Issues

### ZeroConf isn't working

* Make sure the Multicast DNS port (5353) is not being filtered by your network.
* Check the console logs to see which IP adresses `setup_zeroconf` is using.
