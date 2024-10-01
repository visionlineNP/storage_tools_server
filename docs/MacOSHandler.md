# MacOS hanlder

## Install

1. Save this script as `install_foxglovecli_handler.sh`

    ```bash
    #!/bin/bash

    # Define variables
    HANDLER_NAME="foxglovecli-handler"
    APP_NAME="Foxglovecli"
    APP_DIR="$HOME/Applications/$APP_NAME.app"
    SCRIPT_FILE="$APP_DIR/Contents/MacOS/$HANDLER_NAME.sh"

    # Check if Foxglove CLI is installed
    if ! command -v foxglove-studio &> /dev/null; then
        echo "Foxglove CLI not found. Please install it first."
        exit 1
    fi

    # Create the app bundle structure
    echo "Creating the app bundle at $APP_DIR"
    mkdir -p "$APP_DIR/Contents/MacOS"

    # Create the handler script
    echo "Creating handler script at $SCRIPT_FILE"
    cat <<EOF > "$SCRIPT_FILE"
    #!/bin/bash
    # Extract the path from the foxglovecli URL
    path="\${1#foxglovecli://}"

    # Run Foxglove CLI with the extracted path
    foxglove-studio "\$path"
    EOF

    # Make the script executable
    chmod +x "$SCRIPT_FILE"

    # Create the Info.plist file for the app
    PLIST_FILE="$APP_DIR/Contents/Info.plist"
    echo "Creating Info.plist at $PLIST_FILE"
    cat <<EOF > "$PLIST_FILE"
    <?xml version="1.0" encoding="UTF-8"?>
    <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
    <plist version="1.0">
    <dict>
        <key>CFBundleName</key>
        <string>$APP_NAME</string>
        <key>CFBundleIdentifier</key>
        <string>com.example.foxglovecli</string>
        <key>CFBundleVersion</key>
        <string>1.0</string>
        <key>CFBundleExecutable</key>
        <string>foxglovecli-handler.sh</string>
        <key>CFBundlePackageType</key>
        <string>APPL</string>
        <key>CFBundleURLTypes</key>
        <array>
            <dict>
                <key>CFBundleURLName</key>
                <string>Foxglovecli Protocol</string>
                <key>CFBundleURLSchemes</key>
                <array>
                    <string>foxglovecli</string>
                </array>
            </dict>
        </array>
    </dict>
    </plist>
    EOF

    # Register the URL scheme
    echo "Registering the foxglovecli URL scheme"
    osascript -e "do shell script \"lsregister -f $APP_DIR\" with administrator privileges"

    echo "Installation complete. You should now be able to use foxglovecli:// URLs to open files with Foxglove CLI."

    ```

2. Made the file executable, and run script

    ```bash
    chmod +x install_foxglovecli_handler.sh
    ./install_foxglovecli_hanlder.sh
    ```

## Uninstall

1. Save this file as `uninstall_foxglovecli_handler.sh`

    ```bash
    #!/bin/bash

    # Define variables
    APP_NAME="Foxglovecli"
    APP_DIR="$HOME/Applications/$APP_NAME.app"

    # Check if the app exists
    if [ -d "$APP_DIR" ]; then
        echo "Removing the app bundle at $APP_DIR"
        rm -rf "$APP_DIR"
    else
        echo "App bundle not found at $APP_DIR"
    fi

    # Unregister the URL scheme
    echo "Unregistering the foxglovecli URL scheme"
    osascript -e "do shell script \"lsregister -u $APP_DIR\" with administrator privileges"

    echo "Uninstallation complete. The foxglovecli:// URL scheme handler has been removed."

    ```

2. Made the file executable, and run script

    ```bash
    chmod +x uninstall_foxglovecli_handler.sh
    ./uninstall_foxglovecli_hanlder.sh
    ```
