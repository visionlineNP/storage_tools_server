# Key Management

## Adding a New Device

* Log into the Server
* Go to Configure -> Keys

![Screenshot of Configure->Keys](imgs/Keys_01.png)

* Enter a name for the device key in the "Add a new key name" field.
* Click "Generate Key"
* Find the key in the list of keys. Copy the API Key value.
* Open the device `config.yaml` file. Set the `API_KEY_TOKEN` to the key copied from the Server
* Restart the device.

## Adding a Local Server

Terms:
The **Local** server is the application that is running on the user's laptop or workstation.

The **Main** server is the application connected to the main data storage.  

* Log into the **Main** server
* Go to Configure -> Keys
* Enter the **Local** server name in the "Add a new key name" field.
* Click "Generate Key"
* Find the key in the list of keys. Copy the API Key value.
* Log into the **Local** server
* Go to Configure -> Keys
* Paste the key in "Set API KEY TOKEN"
* Click "Set API Key"
