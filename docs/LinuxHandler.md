# Linux Handler

## Install

Set up the browser handler to run `foxglove-studio` from `foxglovecli://` links.

1. Save this file as `install_foxglovecli_handler.sh`.

    ```bash
    #!/bin/bash

    # Define variables
    HANDLER_NAME="foxglovecli-handler"
    DESKTOP_FILE="$HOME/.local/share/applications/${HANDLER_NAME}.desktop"
    SCRIPT_FILE="$HOME/.local/bin/${HANDLER_NAME}.sh"

    # Check if Foxglove Studio is installed
    if ! command -v foxglove-studio &> /dev/null
    then
        echo "Foxglove Studio not found. Please install it first."
        exit 1
    fi

    # Create the handler script
    echo "Creating handler script at $SCRIPT_FILE"
    mkdir -p "$(dirname "$SCRIPT_FILE")"
    cat <<EOF > "$SCRIPT_FILE"
    #!/bin/bash
    # Extract the path from the foxglovecli URL
    path="\${1#foxglovecli://}"

    # Run Foxglove Studio with the extracted path
    foxglove-studio "\$path"
    EOF

    # Make the script executable
    chmod +x "$SCRIPT_FILE"

    # Create the desktop entry file
    echo "Creating desktop entry at $DESKTOP_FILE"
    mkdir -p "$(dirname "$DESKTOP_FILE")"
    cat <<EOF > "$DESKTOP_FILE"
    [Desktop Entry]
    Name=Foxglovecli Handler
    Exec=$SCRIPT_FILE %u
    Type=Application
    MimeType=x-scheme-handler/foxglovecli;
    NoDisplay=true
    EOF

    # Register the foxglovecli:// URL scheme handler
    echo "Registering the foxglovecli URL scheme handler"
    xdg-mime default "$(basename "$DESKTOP_FILE")" x-scheme-handler/foxglovecli

    echo "Installation complete. You should now be able to use foxglovecli:// URLs to open files with Foxglove Studio."
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
    HANDLER_NAME="foxglovecli-handler"
    DESKTOP_FILE="$HOME/.local/share/applications/${HANDLER_NAME}.desktop"
    SCRIPT_FILE="$HOME/.local/bin/${HANDLER_NAME}.sh"

    # Remove the handler script
    if [ -f "$SCRIPT_FILE" ]; then
        echo "Removing handler script at $SCRIPT_FILE"
        rm -f "$SCRIPT_FILE"
    else
        echo "Handler script not found at $SCRIPT_FILE"
    fi

    # Remove the desktop entry file
    if [ -f "$DESKTOP_FILE" ]; then
        echo "Removing desktop entry at $DESKTOP_FILE"
        rm -f "$DESKTOP_FILE"
    else
        echo "Desktop entry not found at $DESKTOP_FILE"
    fi

    # Unregister the foxglovecli URL scheme handler
    echo "Unregistering the foxglovecli URL scheme handler"
    xdg-mime default x-scheme-handler/foxglovecli

    echo "Uninstallation complete. The foxglovecli:// URL scheme handler has been removed."
    ```

2. Made the file executable, and run script

    ```bash
    chmod +x uninstall_foxglovecli_handler.sh
    ./uninstall_foxglovecli_hanlder.sh
    ```
