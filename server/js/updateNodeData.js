// 

function select_new_by_source(event) {
    const caller = event.target;
    const source = caller.dataset.source;
    console.log(source);

    $('input[type="checkbox"][data-page="node"][data-source="' + source + '"][data-on_local="false"][data-on_remote="true"]').prop('checked', true);

}


function sync_files_by_source(event) {
    const caller = event.target;
    const source = caller.dataset.source;

    let selectedUpdateIds = [];
    $('input[type="checkbox"][data-page="node"][data-source="' + source + '"]:checked').each(function () {
        selectedUpdateIds.push($(this).attr('data-upload_id'));
    });

    console.log(selectedUpdateIds);
    if (selectedUpdateIds.length > 0) {
        msg = {
            "source": source,
            "upload_ids": selectedUpdateIds
        }
        socket.emit("transfer_node_files", msg);
    }
}


function processNodeYMD(data) {
    console.log(data)


    const tab_name = data.tab;
    const ymd_div = document.getElementById(tab_name);
    ymd_div.innerHTML = "";

    console.log(data.stats);
    const ymd_name = data.ymd;
    const project_name = data.project;
    const source_name = data.source;



    const run_dl = document.createElement("dl");
    ymd_div.appendChild(run_dl);

    const runs = Object.entries(data.runs);
    runs.sort((a, b) => a[0].localeCompare(b[0]));

    for ([run_name, run_entry] of runs) {
        //console.log(run_name);

        let run_div = document.createElement("div");
        run_dl.appendChild(run_div);

        let run_stats_div = document.createElement("div")
        run_stats_div.className = "container";
        run_div.appendChild(run_stats_div)

        let stats_row_div = document.createElement("div");
        stats_row_div.className = "row align-items-center"
        run_stats_div.appendChild(stats_row_div);
        run_stats_col_1 = document.createElement("div");
        run_stats_col_1.className = "col";
        stats_row_div.appendChild(run_stats_col_1)

        run_stats_col_2 = document.createElement("div");
        run_stats_col_2.className = "col";
        stats_row_div.appendChild(run_stats_col_2)

        stats = data.stats[run_name];
        start_time = stats["start_datetime"];
        end_time = stats["end_datetime"];
        duration = stats["hduration"];
        total_size = stats["htotal_size"];

        let stats_ul = document.createElement("ul");
        run_stats_col_1.appendChild(stats_ul)

        let li = document.createElement("li");
        li.innerHTML = "<b>start</b>: " + start_time;
        stats_ul.appendChild(li);

        li = document.createElement("li");
        li.innerHTML = "<b>duration</b>: " + duration;
        stats_ul.appendChild(li);

        li = document.createElement("li");
        li.innerHTML = "<b>size</b>: " + total_size
        stats_ul.appendChild(li);

        let dtable = document.createElement("table");
        dtable.className = "table table-striped";
        run_stats_col_2.appendChild(dtable)

        let dhead = document.createElement("thead");
        dtable.appendChild(dhead);

        let drow = document.createElement("tr");
        dhead.appendChild(drow);
        drow.appendChild(document.createElement("td"));

        datatypes = Object.entries(stats["datatype"]);
        datatypes.sort((a, b) => a[0].localeCompare(b[0]));

        for ([datatype_name, _] of datatypes) {
            let td = document.createElement("td");
            drow.appendChild(td);
            td.innerHTML = datatype_name;
        }

        let dbody = document.createElement("tbody");
        dtable.appendChild(dbody);

        drow = document.createElement("tr");
        dbody.appendChild(drow);

        td = document.createElement("td");
        td.innerHTML = "<b>Size</b>";
        drow.appendChild(td);
        for ([_, datatype_entry] of datatypes) {
            let td = document.createElement("td");
            drow.appendChild(td);
            td.innerHTML = datatype_entry["htotal_size"];
        }

        drow = document.createElement("tr");
        dbody.appendChild(drow);

        td = document.createElement("td");
        td.innerHTML = "<b>Count</b>";
        drow.appendChild(td);
        for ([_, datatype_entry] of datatypes) {
            let td = document.createElement("td");
            drow.appendChild(td);
            td.innerHTML = datatype_entry["count"];
        }




        const run_dt = document.createElement("dt");
        run_dt.innerHTML = run_name;
        run_dl.appendChild(run_dt);
        const run_dd = document.createElement("dd");
        run_dl.appendChild(run_dd);

        run_entry = Object.entries(run_entry);
        run_entry.sort((a, b) => a[0].localeCompare(b[0]));

        const header_names = ["Select", "Site", "Robot", "Date", "Basename", "Size", "Status"]
        const item_names = ["site", "robot_name", "datetime", "basename", "hsize"]

        const table = document.createElement("table");
        table.className = "table table-striped";
        run_dd.appendChild(table);

        const thead = document.createElement("thead");
        table.appendChild(thead);
        const tr = document.createElement("tr");
        thead.appendChild(tr);

        header_names.forEach((header) => {
            const th = document.createElement("th");
            th.textContent = header;
            tr.appendChild(th);
        });

        const tbody = document.createElement("tbody");
        table.appendChild(tbody);


        for ([relpath, items] of run_entry) {

            const run_header_tr = document.createElement("tr");
            run_header_tr.className = "table-active";
            tbody.appendChild(run_header_tr);

            const run_header_td = document.createElement("td");
            run_header_td.className = "table_relpath"
            run_header_td.setAttribute("colspan", header_names.length);
            run_header_tr.appendChild(run_header_td);

            const relpath_tag = document.createElement("span");
            relpath_tag.className = "table_relpath";
            relpath_tag.innerHTML = relpath;
            run_header_td.appendChild(relpath_tag);

            items.sort((a, b) => a["datetime"].localeCompare(b["datetime"]))

            $.each(items, function (_, detail) {
                const tr = document.createElement("tr");
                tbody.appendChild(tr);


                const tdCheckbox = document.createElement("td");
                const checkbox = document.createElement("input");

                checkbox.dataset.source = source_name;
                checkbox.dataset.datetime = detail.datetime;
                checkbox.dataset.size = detail.size;
                checkbox.dataset.group = "table";
                // switching local and remote!
                checkbox.dataset.on_local = detail.on_remote;
                checkbox.dataset.on_remote = detail.on_local;
                checkbox.dataset.upload_id = detail.upload_id;
                checkbox.dataset.project = project_name;
                checkbox.dataset.offset = detail.offset;
                checkbox.dataset.fullpath = detail.fullpath;
                checkbox.dataset.remote_id = detail.remote_id;

                checkbox.addEventListener("change", (event) => {
                    const source = event.target.dataset.source;
                    updateNodeSelectCounts(source);
                })

                checkbox.type = "checkbox";
                checkbox.id = "server_select_" + detail.upload_id
                tdCheckbox.appendChild(checkbox);
                tr.appendChild(tdCheckbox);


                item_names.forEach((key) => {
                    const td = document.createElement("td");
                    td.innerHTML = detail[key];
                    tr.appendChild(td)

                    if (key == "basename") {
                        if (detail.topics != null && detail.topics.length > 0) {

                            td.innerHTML += "&nbsp;";

                            let dropdown = document.createElement("div");
                            td.appendChild(dropdown);
                            dropdown.className = "dropdown";


                            let caret = document.createElement("i");
                            caret.className = "fas fa-caret-down dropdown-toggle";
                            caret.setAttribute("data-bs-toggle", "dropdown");
                            caret.id = "topics-" + detail.upload_id;
                            caret.setAttribute("aria-expanded", "false");
                            dropdown.appendChild(caret);

                            let dul = document.createElement("ul")
                            dul.className = "dropdown-menu";
                            dul.setAttribute("aria-labelledby", "topics-" + detail.upload_id);
                            dropdown.appendChild(dul);
                            let topics = detail.topics;
                            topics.sort((a, b) => a.localeCompare(b));
                            for (const topic of topics) {
                                let dil = document.createElement("li")
                                dul.appendChild(dil);
                                dil.innerHTML = topic;
                                dil.className = "dropdown-item";
                            }
                        }

                    }

                });

                const tdStatus = document.createElement("td");
                const statusDiv = document.createElement("div");
                statusDiv.id = `node_status_${detail.upload_id}`;
                statusDiv.className = "status-div";

                const onLocal = document.createElement("i")
                onLocal.className = "bi bi-server";
                onLocal.title = "On Local";
                onLocal.id = `node_on_local_${detail.upload_id}`;
                onLocal.setAttribute("data-bs-toggle", "tooltip");
                if (!detail.on_local) {
                    onLocal.title = "Not On Local Server";
                    onLocal.classList.add("grayed-out");
                }
                statusDiv.appendChild(onLocal);

                const onRemote = document.createElement("i")
                onRemote.className = "bi bi-cloud-fill";
                onRemote.title = "On Remote";
                onRemote.id = `node_on_remote_${detail.upload_id}`;
                onRemote.setAttribute("data-bs-toggle", "tooltip");
                if (!detail.on_remote) {
                    onRemote.title = "Not On Remote Server";
                    onRemote.classList.add("grayed-out");
                    onRemote.className = "bi bi-cloud";
                }
                statusDiv.appendChild(onRemote);


                tdStatus.appendChild(statusDiv);
                tr.appendChild(tdStatus);

            });
        }

    };

}


function updateNodeData(data) {
    console.log(data)
    const containerFsInfo = document.getElementById("node-fs-info-container");
    containerFsInfo.innerHTML = ""; // clear previous data

    const ul = document.createElement("ul");
    containerFsInfo.appendChild(ul);

    $.each(data.fs_info, function (_, info) {
        const li = document.createElement("li");
        li.innerHTML = `${info[0]} : <b>${info[1]}%</b> free`;
        ul.appendChild(li);
    });

    const containerData = document.getElementById("node-data-container");
    containerData.innerHTML = ""; // clear previous data

    console.log(data.entries);

    const source_names = Object.keys(data.entries).sort();

    updateNodeCount(source_names.length);


    const source_tabs = create_tabs(source_names, containerData, "node");
    $.each(source_tabs, function (source_name, source_tab) {

        const source_data = data.entries[source_name];
        console.log(source_name, source_data);

        updateNodeStats(source_name, source_tab, data.stats[source_name]["total"])

        const project_names = Object.keys(source_data);
        const project_tabs = create_tabs(project_names, source_tab, "node:" + source_name);
        $.each(project_tabs, function (project_name, project_tab) {

            const div = document.createElement("div");
            project_tab.append(div)

            div.className = 'btn-group';

            const selectAllButton = document.createElement('button');
            selectAllButton.type = 'button';
            selectAllButton.className = 'btn btn-primary';
            // selectAllButton.classList.add("server_button");
            // selectAllButton.id = `select-new-${source_name}-${project_name}`;
            selectAllButton.dataset.source = source_name;
            selectAllButton.dataset.project = project_name;
            selectAllButton.onclick = processNodeSelectAllNew;
            selectAllButton.textContent = 'Select All New';
            div.appendChild(selectAllButton);

            const clearSelectionsButton = document.createElement('button');
            clearSelectionsButton.type = 'button';
            clearSelectionsButton.className = 'btn btn-secondary';
            // clearSelectionsButton.classList.add("server_button");
            // clearSelectionsButton.id = `clear-all-${source_name}-${project_name}`;
            clearSelectionsButton.dataset.source = source_name;
            clearSelectionsButton.dataset.project = project_name;
            clearSelectionsButton.onclick = processClearSelections;
            clearSelectionsButton.textContent = 'Clear Selections';
            div.appendChild(clearSelectionsButton);

            const transferSelectedButton = document.createElement('button');
            transferSelectedButton.type = 'button';
            transferSelectedButton.className = 'btn btn-success';
            // transferSelectedButton.classList.add("server_button");
            //transferSelectedButton.id = `transfer-selected-${source_name}-${project_name}`;
            transferSelectedButton.dataset.source = source_name;
            transferSelectedButton.dataset.project = project_name;
            transferSelectedButton.onclick = processNodeTransferSelections;
            transferSelectedButton.textContent = 'Pull Selected';
            div.appendChild(transferSelectedButton);

            const cancelTransferButton = document.createElement('button');
            cancelTransferButton.type = 'button';
            cancelTransferButton.className = 'btn btn-danger';
            // cancelTransferButton.classList.add("server_button");
            //cancelTransferButton.id = `cancel-${source_name}-${project_name}`;
            cancelTransferButton.dataset.source = source_name;
            cancelTransferButton.dataset.project = project_name;
            cancelTransferButton.onclick = processNodeCancelTransfer;
            cancelTransferButton.textContent = 'Stop Pull';
            div.appendChild(cancelTransferButton);

            const project_data = source_data[project_name];
            const ymd_names = Object.keys(project_data).sort()
            const levels = {}
            ymd_names.forEach(ymd => {
                const { ym, day } = splitYMD(ymd);
                if (levels[ym] == null) { levels[ym] = [ymd] }
                else { levels[ym].push(ymd) }
            });

            const ym_names = Object.keys(levels).sort()
            const ym_tabs = create_tabs(ym_names, project_tab, "node:" + source_name + ":" + project_name + ":ym")

            $.each(ym_tabs, function (ym_name, ym_div) {
                const ymd_names = levels[ym_name];
                const ymd_tabs = create_tabs(ymd_names, ym_div, "node:" + source_name + ":" + project_name, "request_node_ymd_data", true);
                $.each(ymd_tabs, function (_, ymd_div) {
                    add_placeholder(ymd_div);
                })
            })

        });
    })

}

function processNodeSelectAllNew() {
    const source = $(this)[0].dataset.source;
    $('input[type="checkbox"][data-group="table"][data-source="' + source + '"][data-on_local="true"][data-on_remote="false"]').prop('checked', true);
    updateServerSelectCounts(source, "host:Remote");

}


function processNodeTransferSelections() {
    // pull data from remote server to local server.  
    const source = $(this)[0].dataset.source;

    let selectedUpdateIds = [];
    $('input[type="checkbox"][data-group="table"][data-source="' + source + '"]:checked').each(function () {
        const upload_id = $(this).attr('data-upload_id');
        const remote_id = $(this).attr('data-remote_id');
        selectedUpdateIds.push([upload_id, remote_id]);
    });
    console.log(selectedUpdateIds, source);

    msg = {
        "source": source,
        "upload_ids": selectedUpdateIds, "session_token": window.session_token
    }
    socket.emit("transfer_node_files", msg)

}

function processNodeCancelTransfer() {
    const source = $(this)[0].dataset.source;
    socket.emit("request_cancel_node_pull_transfer", { "source": source, "session_token": window.session_token });
}

function updateNodeCount(count) {

    const container = document.getElementById("nodes_menu_status")
    if (container) {
        if (count > 0) {
            container.innerHTML = count;
        } else {
            container.innerHTML = "";
        }
    } else {
        console.log("did not find 'node_menu_status'")
    }
}


function updateNodeStats(source_name, source_tab, stats) {
    //const source_tab = document.getElementById(tab_name)

    let div = document.getElementById(source_name + "_node_file_stats");

    if (div == null) {
        div = document.createElement("div");
        div.id = source_name + "_node_file_stats";
        source_tab.append(div);
    } else {
        div.innerHTML = "";
    }

    const dtable = document.createElement("table");
    div.appendChild(dtable);

    dtable.className = "table table-striped";

    let dhead = document.createElement("thead");
    dtable.appendChild(dhead);

    let drow = document.createElement("tr");
    dhead.appendChild(drow);


    drow.appendChild(document.createElement("td"));

    let td = document.createElement("td");
    drow.appendChild(td);
    td.innerHTML = "Total";

    datatypes = Object.entries(stats["datatype"]);
    datatypes.sort((a, b) => a[0].localeCompare(b[0]));

    for ([datatype_name, _] of datatypes) {
        let td = document.createElement("td");
        drow.appendChild(td);
        td.innerHTML = datatype_name;
    }

    td = document.createElement("td")
    td.innerHTML = "Selected"
    drow.appendChild(td)


    let dbody = document.createElement("tbody");
    dtable.appendChild(dbody);

    drow = document.createElement("tr");
    dbody.appendChild(drow);

    td = document.createElement("td");
    td.innerHTML = "<b>Size</b>";
    drow.appendChild(td);

    td = document.createElement("td");

    td.innerHTML = stats["htotal_size"];
    drow.appendChild(td);

    for ([_, datatype_entry] of datatypes) {
        let td = document.createElement("td");
        drow.appendChild(td);
        td.innerHTML = datatype_entry["htotal_size"];
    }

    td = document.createElement("td");
    td.id = source_name + "_selected_hsize"
    td.innerHTML = "0 B"
    drow.appendChild(td)

    drow = document.createElement("tr");
    dbody.appendChild(drow);

    td = document.createElement("td");
    td.innerHTML = "<b>Count</b>";
    drow.appendChild(td);

    td = document.createElement("td");
    td.innerHTML = stats["count"];
    drow.appendChild(td);


    for ([_, datatype_entry] of datatypes) {
        let td = document.createElement("td");
        drow.appendChild(td);
        td.innerHTML = datatype_entry["count"];
    }

    td = document.createElement("td");
    td.id = source_name + "_selected_count"
    td.innerHTML = "0"
    drow.appendChild(td)
}

/**
 * 
 * @param {string} source source name 
 */
function updateNodeSelectCounts(source) {
    let total_size = 0;
    let total_count = 0;
    $('input[type="checkbox"][data-group="table"][data-source="' + source + '"]:checked').each(function () {
        total_count += 1;
        total_size += parseInt($(this).attr("data-size"));
    });
    let hsize = formatBytes(total_size);
    console.log(total_count, total_size, hsize)

    let span = document.getElementById(source + "_selected_hsize")
    if (span) {
        span.innerHTML = hsize;
    } else {
        const tn = source + "_selected_hsize"
        console.log("did not find " + tn)
    }

    span = document.getElementById(source + "_selected_count")
    if (span) {
        span.innerHTML = total_count;
    }
}

function processNodeClearSelections() {
    const source = $(this)[0].dataset.source;

    $('input[type="checkbox"][data-group="table"][data-source="' + source + '"]:checked').prop('checked', false);
    updateNodeSelectCounts(source)

}
