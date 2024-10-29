
// tab_names is list of names
// parent is div element to attach the tabs
// prefix is name for the bs-target

function create_tabs(names, parent, prefix, event = null, auto_trigger = false) {
    session_token = window.session_token

    rtn = {}

    const tablist = document.createElement("ul");
    tablist.className = "nav nav-tabs";
    tablist.role = "tablist"
    parent.appendChild(tablist)

    let first_name = true;
    let first_tab = false;
    for (const item_name of names) {
        let li = document.createElement("li");
        li.className = "nav-item";
        li.role = "presentation";
        let link = document.createElement("a");
        li.appendChild(link);

        link.innerHTML = item_name;
        tablist.appendChild(li)

        if (first_name) {
            link.className = "nav-link active";
            link.setAttribute("aria-selected", "true")
            link.setAttribute("data-tigger", false)
            first_name = false;
        } else {
            link.className = "nav-link";
            link.setAttribute("data-trigger", true)
        }
        const tab_name = prefix + ":" + item_name;
        link.setAttribute("data-bs-toggle", "tab");
        link.setAttribute("data-bs-target", "#" + tab_name);
        link.type = "button";
        link.role = "tab";
        link.setAttribute("aria-controls", tab_name);

        if (event && !auto_trigger && !first_name) {
            // execute this function once the tab is visible for the first time
            link.addEventListener("show.bs.tab", function (e) {
                //console.log(e, event, tab_name, session_token);
                if ($(this)[0].dataset.trigger) {
                    socket.emit(event, { tab: tab_name, session_token: session_token })
                }
            }, { once: true })
        }
        first_tab = false;
    }

    const tab_contents = document.createElement("div");
    tab_contents.className = "tab-content";
    parent.appendChild(tab_contents);
    first_name = true;
    for (const item_name of names) {
        let was_first = false;
        let tab_div = document.createElement("div");
        tab_contents.appendChild(tab_div);
        if (first_name) {
            tab_div.className = "tab-pane fade show active";
            first_name = false;
            was_first = true;
        } else {
            tab_div.className = "tab-pane fade hidden";
        }
        const tab_name = prefix + ":" + item_name;
        tab_div.id = tab_name;
        tab_div.role = "tabpanel";
        tab_div.setAttribute("aria-labelledby", tab_name);
        tab_div.tabIndex = "0";

        rtn[item_name] = tab_div;

        if (event && (was_first || auto_trigger)) {
            // always make sure the first one is triggered. 
            console.log(event, tab_name);
            socket.emit(event, { tab: tab_name, session_token: session_token })
        }
    }

    return rtn;
}


function add_single_tab(full_tab_name, event = null) {
    const levels = full_tab_name.split(':');
    const current_level_name = levels.shift(); // Extract the current level
    const remaining_levels = levels.join(':'); // Remaining levels after this one

    // Assume the top-level tab is always present
    let current_parent = document.getElementById(current_level_name);
    if (!current_parent) {
        console.error(`Top-level tab container "${current_level_name}" does not exist.`);
        return null;
    }

    // Ensure there is a tab list in the current parent
    let tablist = current_parent.querySelector('ul.nav.nav-tabs');
    if (!tablist) {
        tablist = document.createElement("ul");
        tablist.className = "nav nav-tabs";
        tablist.role = "tablist";
        current_parent.appendChild(tablist);
    }

    // Ensure there is a tab content container in the current parent
    let tab_contents = current_parent.querySelector('.tab-content');
    if (!tab_contents) {
        tab_contents = document.createElement("div");
        tab_contents.className = "tab-content";
        current_parent.appendChild(tab_contents);
    }

    // If there are more levels to traverse, call this function recursively
    if (remaining_levels) {
        let next_level_id = `${current_level_name}:${levels[0]}`;
        let next_level_tab_content = document.getElementById(next_level_id);

        // If the next level doesn't exist, create it
        if (!next_level_tab_content) {
            next_level_tab_content = document.createElement("div");
            next_level_tab_content.id = next_level_id;
            next_level_tab_content.className = "tab-pane fade hidden";
            next_level_tab_content.role = "tabpanel";
            next_level_tab_content.setAttribute("aria-labelledby", next_level_id);
            next_level_tab_content.tabIndex = "0";
            tab_contents.appendChild(next_level_tab_content);

            // Also add the tab item in the nav
            let li = document.createElement("li");
            li.className = "nav-item";
            li.role = "presentation";

            let link = document.createElement("a");
            link.className = "nav-link";
            link.innerHTML = levels[0]; // Use the current level name
            link.setAttribute("data-bs-toggle", "tab");
            link.setAttribute("data-bs-target", `#${next_level_id}`);
            link.type = "button";
            link.role = "tab";
            link.setAttribute("aria-controls", next_level_id);

            li.appendChild(link);
            tablist.appendChild(li);
        }

        // Continue the recursion to process the remaining levels
        return add_single_tab(full_tab_name, event);
    } else {
        // We are at the leaf (final) level, create the tab if it doesn't exist
        let leaf_tab = document.getElementById(full_tab_name);
        if (!leaf_tab) {
            // Create the tab content container
            leaf_tab = document.createElement("div");
            leaf_tab.id = full_tab_name;
            leaf_tab.className = "tab-pane fade hidden";
            leaf_tab.role = "tabpanel";
            leaf_tab.setAttribute("aria-labelledby", full_tab_name);
            leaf_tab.tabIndex = "0";
            tab_contents.appendChild(leaf_tab);

            // Also add the tab item to the nav list
            let li = document.createElement("li");
            li.className = "nav-item";
            li.role = "presentation";

            let link = document.createElement("a");
            link.className = "nav-link";
            link.innerHTML = current_level_name; // Use the current level name
            link.setAttribute("data-bs-toggle", "tab");
            link.setAttribute("data-bs-target", `#${full_tab_name}`);
            link.type = "button";
            link.role = "tab";
            link.setAttribute("aria-controls", full_tab_name);

            // Add the event only on the leaf tab
            if (event) {
                link.addEventListener("show.bs.tab", function (e) {
                    console.log(e, event, full_tab_name, session_token);
                    socket.emit(event, { tab: full_tab_name, session_token: window.session_token });
                }, { once: true });
            }

            li.appendChild(link);
            tablist.appendChild(li);
        }

        return leaf_tab; // Return the final tab content div
    }
}



function add_placeholder(div) {
    const p = document.createElement("p");
    p.className = "placeholder-glow";
    p.setAttribute("aria-hidden", "true");
    div.appendChild(p);
    const rows = [[7, 4, 2], [8, 4, 4], [6, 9, 3]];
    $.each(rows, function (_, sizes) {
        $.each(sizes, function (_, sz) {
            const span = document.createElement("span");
            p.appendChild(span);
            span.className = "placeholder col-" + sz;

            const space = document.createElement("span");
            p.append(space);
            space.textContent = " ";
        });
        const br = document.createElement("br")
        p.append(br);
    });

}


function createFileSizeRangeSelector(minBytes, maxBytes, sizeSelectorDiv, name) {
    // Convert bytes to human-readable format
    function bytesToHumanReadable(bytes) {
        const units = ['B', 'KB', 'MB', 'GB', 'TB'];
        let index = 0;
        let readableSize = bytes;

        while (readableSize >= 1024 && index < units.length - 1) {
            readableSize /= 1024;
            index++;
        }

        return `${readableSize.toFixed(2)} ${units[index]}`;
    }

    // Create label and input for the minimum size
    const minLabel = document.createElement('label');
    minLabel.textContent = `Min Size (${bytesToHumanReadable(minBytes)}): `;
    minLabel.setAttribute('for', "filter-" + name + '-minSize');

    const minInput = document.createElement('input');
    minInput.type = 'range';
    minInput.id = "filter-" + name + '-minSize';
    minInput.min = minBytes;
    minInput.max = maxBytes;
    minInput.value = minBytes;
    minInput.step = 1;

    // Create label and input for the maximum size
    const maxLabel = document.createElement('label');
    maxLabel.textContent = `Max Size (${bytesToHumanReadable(maxBytes)}): `;
    maxLabel.setAttribute('for', "filter-" + name + '-maxSize');

    const maxInput = document.createElement('input');
    maxInput.type = 'range';
    maxInput.id = "filter-" + name + '-maxSize';
    maxInput.min = minBytes;
    maxInput.max = maxBytes;
    maxInput.value = maxBytes;
    maxInput.step = 1;

    // Display the selected range
    const rangeDisplay = document.createElement('div');
    rangeDisplay.id = "filter-" + name + '-rangeDisplay';
    rangeDisplay.textContent = `Selected Range: ${bytesToHumanReadable(minBytes)} - ${bytesToHumanReadable(maxBytes)}`;

    // Update the display whenever the sliders change
    function updateRangeDisplay() {
        let minSize = parseInt(minInput.value, 10);
        let maxSize = parseInt(maxInput.value, 10);

        // Ensure minSize is not greater than maxSize
        if (minSize > maxSize) {
            if (this === minInput) {
                maxInput.value = minSize;
                maxSize = minSize;
            } else {
                minInput.value = maxSize;
                minSize = maxSize;
            }
        }

        sizeSelectorDiv.dataset.min = minSize;
        sizeSelectorDiv.dataset.max = maxSize;

        rangeDisplay.textContent = `Selected Range: ${bytesToHumanReadable(minSize)} - ${bytesToHumanReadable(maxSize)}`;
    }

    minInput.addEventListener('input', updateRangeDisplay);
    maxInput.addEventListener('input', updateRangeDisplay);

    // Append elements to the size_selector div
    sizeSelectorDiv.appendChild(minLabel);
    sizeSelectorDiv.appendChild(minInput);
    sizeSelectorDiv.appendChild(document.createElement('br')); // Line break
    sizeSelectorDiv.appendChild(maxLabel);
    sizeSelectorDiv.appendChild(maxInput);
    sizeSelectorDiv.appendChild(document.createElement('br')); // Line break
    sizeSelectorDiv.appendChild(rangeDisplay);

    sizeSelectorDiv.dataset.type = "range"
    sizeSelectorDiv.dataset.group = "filter"
    sizeSelectorDiv.dataset.name = name
    sizeSelectorDiv.dataset.min = minBytes;
    sizeSelectorDiv.dataset.max = maxBytes;

    function reset() {
        minInput.value = minBytes;
        maxInput.value = maxBytes

        sizeSelectorDiv.dataset.min = minBytes;
        sizeSelectorDiv.dataset.max = maxBytes;
    }

    sizeSelectorDiv.reset = reset;

}

function createFileDurationRangeSelector(minSeconds, maxSeconds, sizeSelectorDiv, name) {
    // Convert seconds to human-readable format
    function secondsToHumanReadable(seconds) {
        const units = ['sec', 'min', 'hours', 'days'];
        let index = 0;
        let readableTime = seconds;

        // Convert seconds to the appropriate unit
        while (readableTime >= 60 && index < units.length - 1) {
            if (index === 0) {
                readableTime /= 60;  // Convert to minutes
            } else if (index === 1) {
                readableTime /= 60;  // Convert to hours
            } else if (index === 2) {
                readableTime /= 24;  // Convert to days
            }
            index++;
        }

        return `${readableTime.toFixed(2)} ${units[index]}`;
    }

    // Create label and input for the minimum size
    const minLabel = document.createElement('label');
    minLabel.textContent = `Min Duration (${secondsToHumanReadable(minSeconds)}): `;
    minLabel.setAttribute('for', "filter-" + name + '-minSize');

    const minInput = document.createElement('input');
    minInput.type = 'range';
    minInput.id = "filter-" + name + '-minSize';
    minInput.min = minSeconds;
    minInput.max = maxSeconds;
    minInput.value = minSeconds;
    minInput.step = 1;

    // Create label and input for the maximum size
    const maxLabel = document.createElement('label');
    maxLabel.textContent = `Max Duration (${secondsToHumanReadable(maxSeconds)}): `;
    maxLabel.setAttribute('for', "filter-" + name + '-maxSize');

    const maxInput = document.createElement('input');
    maxInput.type = 'range';
    maxInput.id = "filter-" + name + '-maxSize';
    maxInput.min = minSeconds;
    maxInput.max = maxSeconds;
    maxInput.value = maxSeconds;
    maxInput.step = 1;

    // Display the selected range
    const rangeDisplay = document.createElement('div');
    rangeDisplay.id = "filter-" + name + '-rangeDisplay';
    rangeDisplay.textContent = `Selected Range: ${secondsToHumanReadable(minSeconds)} - ${secondsToHumanReadable(maxSeconds)}`;

    // Update the display whenever the sliders change
    function updateRangeDisplay() {
        let minSize = parseInt(minInput.value, 10);
        let maxSize = parseInt(maxInput.value, 10);

        // Ensure minSize is not greater than maxSize
        if (minSize > maxSize) {
            if (this === minInput) {
                maxInput.value = minSize;
                maxSize = minSize;
            } else {
                minInput.value = maxSize;
                minSize = maxSize;
            }
        }

        sizeSelectorDiv.dataset.min = minSize;
        sizeSelectorDiv.dataset.max = maxSize;

        rangeDisplay.textContent = `Selected Range: ${secondsToHumanReadable(minSize)} - ${secondsToHumanReadable(maxSize)}`;
    }

    minInput.addEventListener('input', updateRangeDisplay);
    maxInput.addEventListener('input', updateRangeDisplay);

    // Append elements to the size_selector div
    sizeSelectorDiv.appendChild(minLabel);
    sizeSelectorDiv.appendChild(minInput);
    sizeSelectorDiv.appendChild(document.createElement('br')); // Line break
    sizeSelectorDiv.appendChild(maxLabel);
    sizeSelectorDiv.appendChild(maxInput);
    sizeSelectorDiv.appendChild(document.createElement('br')); // Line break
    sizeSelectorDiv.appendChild(rangeDisplay);

    sizeSelectorDiv.dataset.type = "range"
    sizeSelectorDiv.dataset.group = "filter"
    sizeSelectorDiv.dataset.name = name
    sizeSelectorDiv.dataset.min = minSeconds;
    sizeSelectorDiv.dataset.max = maxSeconds;

    function reset() {
        minInput.value = minSeconds;
        maxInput.value = maxSeconds

        sizeSelectorDiv.dataset.min = minSeconds;
        sizeSelectorDiv.dataset.max = maxSeconds;
    }

    sizeSelectorDiv.reset = reset;
}


function getCookie(name) {
    let cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
        let cookie = cookies[i].trim();
        // Check if this cookie matches the name we are looking for
        if (cookie.startsWith(name + '=')) {
            return decodeURIComponent(cookie.substring(name.length + 1));
        }
    }
    return null;
}

// Function to delete a specific cookie by name
function deleteCookie(name) {
    document.cookie = name + '=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
}


function setCookie(name, value, days) {
    // Read all existing cookies
    const existingCookies = document.cookie.split(';').reduce((cookies, cookieString) => {
        const [key, val] = cookieString.split('=').map(c => c.trim());
        cookies[key] = val;
        return cookies;
    }, {});

    // Update or add the specified cookie
    existingCookies[name] = encodeURIComponent(value);

    // Set the expiration date if 'days' parameter is provided
    let expires = "";
    if (days) {
        const date = new Date();
        date.setTime(date.getTime() + (days * 24 * 60 * 60 * 1000));
        expires = "; expires=" + date.toUTCString();
    }

    // Rewrite all cookies, including the updated one
    for (const [key, val] of Object.entries(existingCookies)) {
        document.cookie = `${key}=${val}${expires}; path=/`;
    }
}


function formatBytes(bytes) {
    const units = ["B", "KB", "MB", "GB", "TB"];
    let unitIndex = 0;

    // Convert bytes to a larger unit until it's below 1024
    while (bytes >= 1000 && unitIndex < units.length - 1) {
        bytes /= 1000;
        unitIndex++;
    }

    return `${bytes.toFixed(2)} ${units[unitIndex]}`;
}