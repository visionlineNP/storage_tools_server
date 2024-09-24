
// tab_names is list of names
// parent is div element to attach the tabs
// prefix is name for the bs-target

function create_tabs(names, parent, prefix, event=null)
{
    session_token = window.session_token

    rtn = {}

    const tablist = document.createElement("ul");
    tablist.className = "nav nav-tabs";
    tablist.role = "tablist"
    parent.appendChild(tablist)

    let first_name = true;
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
            first_name = false;
        } else {
            link.className = "nav-link";
        }
        const tab_name = prefix + ":" + item_name;
        link.setAttribute("data-bs-toggle", "tab");
        link.setAttribute("data-bs-target", "#" + tab_name);
        link.type = "button";
        link.role = "tab";
        link.setAttribute("aria-controls", tab_name);

        if(event) {
            // execute this function once the tab is visible for the first time
            link.addEventListener("show.bs.tab", function(e) {
                // console.log(e, event, tab_name);
                socket.emit(event, {tab:tab_name, session_token: session_token})
            },{once: true})
        }
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

        if(event && was_first) {
            // always make sure the first one is triggered. 
            // console.log(event, tab_name);
            socket.emit(event, {tab:tab_name, session_token: session_token})
        }
    }

    return rtn;
}

function add_placeholder(div)
{
    const p = document.createElement("p");
    p.className = "placeholder-glow";
    p.setAttribute("aria-hidden", "true");
    div.appendChild(p);
    const sizes = [7,4, 2, 8, 4,4,6,9];
    $.each(sizes, function(_, sz) {
        const span = document.createElement("span");
        p.appendChild(span);
        span.className = "placeholder col-" + sz;

        const space = document.createElement("span");
        p.append(space);
        space.textContent = " ";
    });

}


function createFileSizeRangeSelector(minBytes, maxBytes, sizeSelectorDiv, name ) {
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
}

function createFileDurationRangeSelector(minSeconds, maxSeconds, sizeSelectorDiv, name ) {
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

}