var search_current_page = 0;
var search_total_pages = 0;
var search_current_index = 0;
// this should be a selectable option
var results_per_page = 15;

var search_sort_name = "datetime";
var search_sort_direction = "forward"


function searchPrevPage() {
    console.log("Prev")

    const start_idx = parseInt(search_current_index) - parseInt(results_per_page);

    room = "dashboard-" + window.session_token;
    msg = {
        "room": room,
        "start_index": start_idx,
        "count": results_per_page
    }
    socket.emit("search_fetch", msg)

}


function searchNextPage() {
    console.log("next")

    const start_idx = parseInt(search_current_index) + parseInt(results_per_page);

    room = "dashboard-" + window.session_token;
    msg = {
        "room": room,
        "start_index": start_idx,
        "count": results_per_page
    }
    socket.emit("search_fetch", msg)

}

function updateSearchFilters(msg) {
    console.log("update search filters", msg);
    const container = document.getElementById("search-filter")
    if (!container) {
        console.log("Could not find search-filter")
        return;
    }
    container.innerHTML = "";
    container.className = "accordion accordion-flush"
    $.each(msg, function (name, entry) {
        //console.log(name, entry);
        const cord_item = document.createElement("div")
        cord_item.className = "accordion-item"
        container.appendChild(cord_item)
        const cord_header = document.createElement("h3")
        cord_header.className = "accordion-header";
        cord_item.appendChild(cord_header)
        const button = document.createElement("button")
        button.className = "accordion-button collapsed"
        button.type = "button"
        button.setAttribute("data-bs-toggle", "collapse");
        //  aria-expanded="false" aria-controls="flush-collapseOne">
        button.setAttribute("data-bs-target", "#filter-" + name)
        button.setAttribute("aria-expanded", "false")
        button.setAttribute("aria-controls", "filter-" + name)
        button.innerHTML = name
        cord_header.append(button)

        const cord_flush = document.createElement("div")
        // <div id="flush-collapseOne" class="accordion-collapse collapse" data-bs-parent="#accordionFlushExample">
        cord_item.appendChild(cord_flush)
        cord_flush.id = "filter-" + name
        cord_flush.className = "accordion-collapse collapse"
        cord_flush.setAttribute("data-bs-parent", "search-filter")
        const cord_body = document.createElement("div")
        cord_flush.append(cord_body)
        cord_body.className = "accordion-body"

        if (entry.type == "discrete") {
            $.each(entry.keys, function (_, filter_item) {
                const checkbox = document.createElement("input");
                checkbox.type = "checkbox"
                checkbox.dataset.filter = name
                checkbox.dataset.value = filter_item
                checkbox.dataset.group = "filter"
                checkbox.id = "filter-" + name + "-" + filter_item;
                cord_body.appendChild(checkbox)

                const label = document.createElement("label");
                label.for = "filter-" + name + "-" + filter_item;
                label.innerHTML = filter_item
                cord_body.appendChild(label);
                cord_body.appendChild(document.createElement("br"))
            });
        } else {
            if (name == "datetime") {
                const start_time = entry.min
                const end_time = entry.max
                createDatetimeRangeSelector(start_time, end_time, cord_body, name);
            } 
            if( name == "size") {
                const minBytes = entry.min;
                const maxBytes = entry.max;

                createFileSizeRangeSelector(minBytes, maxBytes, cord_body, name)               
            }

            if( name == "duration") {
                const minSec = entry.min;
                const maxSec = entry.max;
                createFileDurationRangeSelector(minSec, maxSec, cord_body, name);
            }
        }
    })
}

function createDatetimeRangeSelector(start_time_, end_time_, cord_body, name) {

    const start_time = start_time_.replace(" ", "T");
    const end_time = end_time_.replace(" ", "T");

    // Create label and input for start datetime
    const startLabel = document.createElement('label');
    startLabel.textContent = 'Start Datetime: ';
    startLabel.setAttribute('for', 'filter-startDatetime');

    const startInput = document.createElement('input');
    startInput.type = 'datetime-local';
    startInput.id = 'filter-startDatetime';
    startInput.value = start_time;
    startInput.min = start_time;
    startInput.max = end_time;

    // Create label and input for end datetime
    const endLabel = document.createElement('label');
    endLabel.textContent = 'End Datetime: ';
    endLabel.setAttribute('for', 'filter-endDatetime');

    const endInput = document.createElement('input');
    endInput.type = 'datetime-local';
    endInput.id = 'filter-endDatetime';
    endInput.value = end_time;
    endInput.min = start_time;
    endInput.max = end_time;

    cord_body.appendChild(startLabel);
    cord_body.appendChild(startInput);
    cord_body.appendChild(document.createElement("br"));
    cord_body.appendChild(endLabel);
    cord_body.appendChild(endInput);

    cord_body.dataset.type = "range";
    cord_body.dataset.group = "filter";
    cord_body.dataset.name = name;
    cord_body.dataset.min = start_time.replace("T", " ");
    cord_body.dataset.max = end_time.replace("T", " ");

    startInput.addEventListener('input', updateRangeDisplay);
    endInput.addEventListener('input', updateRangeDisplay);

    function updateRangeDisplay() {
        const start_time = startInput.value;
        const end_time = endInput.value;
        cord_body.dataset.min = start_time.replace("T", " ");
        cord_body.dataset.max = end_time.replace("T", " ");
    }

    function reset() {
        startInput.value = start_time_.replace(" ", "T");
        endInput.value = end_time.replace(" ", "T");

        cord_body.dataset.min = start_time_;
        cord_body.dataset.max = end_time_;
    }
    cord_body.reset = reset;
}

function updateSearchResults(msg) {
    console.log(msg);
    const keys = ["select", "project", "site", "robot_name", "datetime", "basename", "path", "hsize"];

    search_total_pages = msg.total_pages;
    search_current_page = msg.current_page;
    search_current_index = msg.current_index;

    const page_number = document.getElementById("search-current-page")
    const current_page_display = 1 + parseInt(search_current_page)
    page_number.innerHTML = current_page_display + " / " + search_total_pages;

    document.getElementById("search-prev-page").disabled = (search_current_page == 0);
    document.getElementById("search-next-page").disabled = (search_current_page >= (search_total_pages - 1));

    const results = msg.results;

    const search_body = document.getElementById("search-body");
    if (!search_body) {
        console.log("Failed to find search-body")
        return;
    }
    search_body.innerHTML = "";
    results.forEach(searchRow => {
        const tr = document.createElement("tr");
        search_body.appendChild(tr);
        keys.forEach(key => {
            const td = document.createElement("td");
            tr.appendChild(td);
            if (key == "select") {
                // pass for now
            } else if( key == "path") {
                td.innerHTML = "";
                const icon = document.createElement("i")
                icon.className = "bi bi-copy"
                icon.title = "Copy to clipboard: " + searchRow.localpath;
                icon.dataset.localpath = searchRow.localpath;
                icon.setAttribute("data-bs-toggle", "tooltip");

                icon.addEventListener('click', function () {
                    const localpath = $(this)[0].dataset.localpath;
                    navigator.clipboard.writeText(localpath);
                })

                td.appendChild(icon)


                const download = document.createElement("i")
                download.className = "bi bi-download"
                download.title = "Download "
                download.dataset.upload_id = searchRow.upload_id;
                download.dataset.basename = searchRow.basename;
                download.setAttribute("data-bs-toggle", "tooltip");
                download.addEventListener("click", function () {
                    const upload_id = $(this)[0].dataset.upload_id;
                    const basename = $(this)[0].dataset.basename;

                    const link = document.createElement("a")
                    link.href = `/download/${upload_id}`
                    link.download = basename;
                    link.style.display = 'none';

                    document.body.appendChild(link);
                    link.click()
                    document.body.removeChild(link);

                })
                const spacer = document.createElement("span");
                spacer.innerHTML = "&nbsp;&nbsp;"
                td.appendChild(spacer)
                td.appendChild(download);


            } else {

                td.innerHTML = searchRow[key]

                if (key == "basename") {
                    let topics = null;
                    if (searchRow.topics) {
                        topics = Object.entries(searchRow.topics)
                    }

                    if (topics && topics.length > 0) {

                        td.innerHTML += "&nbsp;";

                        let dropdown = document.createElement("div");
                        td.appendChild(dropdown);
                        dropdown.className = "dropdown";


                        let caret = document.createElement("i");
                        caret.className = "fas fa-caret-down dropdown-toggle";
                        caret.setAttribute("data-bs-toggle", "dropdown");
                        caret.id = "topics-" + searchRow.upload_id;
                        caret.setAttribute("aria-expanded", "false");
                        dropdown.appendChild(caret);

                        let dul = document.createElement("ul")
                        dul.className = "dropdown-menu";
                        dul.setAttribute("aria-labelledby", "topics-" + searchRow.upload_id);
                        dropdown.appendChild(dul);
                        topics.sort((a, b) => a[0].localeCompare(b[0]));
                        for (const [topic, topic_count] of topics) {
                            let dil = document.createElement("li");
                            dul.appendChild(dil);
                            dil.innerHTML = topic + " : (" + topic_count + ")";
                            dil.className = "dropdown-item";
                        }

                    }

                }

            }
        });
    });

}

function readFilter()
{
    let selected = {};
    $('input[type="checkbox"][data-group="filter"]:checked').each(function () {
        const name = $(this).attr('data-filter');
        const value = $(this).attr('data-value');
        if( selected[name] ) {
            selected[name]["keys"].push(value);
        } else {
            selected[name] = {
                "type": "discrete",
                "keys": [value]
            }
        }
        //selectedUpdateIds.push($(this).attr('id'));
      });    

      $('div[data-group="filter"][data-type="range"').each(function() {
        const name = $(this).attr('data-name');
        const minVal = $(this).attr('data-min');        
        const maxVal = $(this).attr('data-max');   
        selected[name] = {
            "type": "range",
            "min": minVal,
            "max": maxVal
        }
      })
      return selected;
}

function startNewSearch() {
    search_current_page = 0;

    filter = readFilter();
    console.log(filter);

    room = "dashboard-" + window.session_token;
    msg = {
        "room": room,
        "filter": filter,
        "sort-key": search_sort_name,
        "sort-direction": search_sort_direction,
        "results-per-page": results_per_page
    }
    socket.emit("search", msg)
}

function setSearchSort(name) {
    const prior_icon = document.getElementById("search-sort-" + search_sort_name + "-dir")
    const selected_icon = document.getElementById("search-sort-" + name + "-dir")

    if( name == search_sort_name) {
        if( search_sort_direction == "forward") {
            search_sort_direction = "reverse"
            selected_icon.className = "bi bi-caret-up-fill"
        } else {
            search_sort_direction = "forward"
            selected_icon.className = "bi bi-caret-down-fill"
        }
    } else {
        prior_icon.className = ""
        search_sort_name = name 
        search_sort_direction = "forward"
        selected_icon.className = "bi bi-caret-down-fill"
    }
    startNewSearch()
}


function clearAllFilters() {
    $('input[type="checkbox"][data-group="filter"]:checked').prop('checked', false);  
    
    $('div[data-group="filter"][data-type="range"').each(function() {
        $(this)[0].reset()
    })
}


function updateSearchItemsPerPage() 
{
    const select = document.getElementById("search-items-per-page");
    results_per_page = select.value;
}