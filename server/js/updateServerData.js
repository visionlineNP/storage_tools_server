function on_dashboard_update(data) {
    msg = {
        "upload_id": data.upload_id,
        "on_remote": data.on_server,
        "on_local": data.on_device
    }
    on_dashboard_file_server(msg)
}


function on_dashboard_file_server(data) {
    let upload_id = data.upload_id;

    let onRemote = document.getElementById("on_remote_" + upload_id);
    if (onRemote) {
        if (data.on_remote) {
            onRemote.className = "bi bi-cloud-fill";
            onRemote.classList.add("remote_icon");
            onRemote.classList.remove("grayed-out");
            onRemote.title = "On Remote Server";
        } else {
            onRemote.className = "bi bi-cloud";
            onRemote.classList.add("remote_icon");
            onRemote.classList.add("grayed-out");
            onRemote.title = "Not On Remote Server";
        }
    } else { console.log("didnt find ", "on_remote_" + upload_id) }

    let onLocal = document.getElementById("on_local_" + upload_id);
    if (onLocal) {
        if (data.on_local) {
            onLocal.classList.remove("grayed-out");
            onLocal.title = "On Local";
        } else {
            onLocal.classList.add("grayed-out");
            onLocal.title = "Not On Local";
        }
    } else { console.log("didnt find ", "on_local_" + upload_id) }

    let checkbox = document.getElementById("server_select_" + upload_id)
    if (checkbox) {
        checkbox.dataset.on_local = data.on_local;
        checkbox.dataset.on_remote = data.on_remote;
        refreshTooltips();
    } else {
        console.log("Did not find ", "server_select_" + upload_id)
    }
}

function on_remote_connection(msg) {
    const sync_status = document.getElementById("sync_status");
    const link_button = document.getElementById("link_button");
    if (sync_status && link_button) {
        if (msg.connected) {
            sync_status.className = "bi bi-cloud-fill";
            sync_status.title = "Connected";
            link_button.dataset.connected = true;
            link_button.textContent = "Disconnect";

        } else {
            sync_status.className = "bi bi-cloud grayed-out";
            sync_status.title = "Disconnected";
            link_button.dataset.connected = false;
            link_button.textContent = "Connect";
        }

        const syncButtons = document.querySelectorAll(".server_button");
        syncButtons.forEach(function (button) {
            button.disabled = !msg.connected;
        })

        // const remoteIcons = document.querySelectorAll(".remote_icon");
        // remoteIcons.forEach(function (icon) {
        //     icon.disabled = !msg.connected;
        // })

        refreshTooltips();
    }
    const refresh_button = document.getElementById("refresh_button");
    if (refresh_button) {
        refresh_button.disabled = !msg.connected;
    }
}

function processServerSelectAllNew() {
    const source = $(this)[0].dataset.source;
    $('input[type="checkbox"][data-group="table"][data-source="' + source + '"][data-on_local="true"][data-on_remote="false"]').prop('checked', true);

}

function processServerStatus(data) {
    const msg = data.msg;
    const div = document.getElementById("server-status");
    if (!div) {
        console.log("Did not find 'server-status'");
        return
    }
    div.innerHTML = "";
    if (msg.size() > 1) {
        div.innerHTML = "<span>" + msg + "</span>"
    }

}

function processServerTransferSelections() {
    const source = $(this)[0].dataset.source;

    let selectedUpdateIds = [];
    $('input[type="checkbox"][data-group="table"][data-source="' + source + '"]:checked').each(function () {
        selectedUpdateIds.push($(this).attr('data-upload_id'));
    });
    console.log(selectedUpdateIds, source);

    msg = {
        "source": source,
        "upload_ids": selectedUpdateIds, "session_token": window.session_token
    }
    socket.emit("server_transfer_files", msg)
}


function processServerCancelTransfer() {
    const source = $(this)[0].dataset.source;
    socket.emit("control_msg", { "source": source, "action": "cancel", "session_token": window.session_token });

}


window.server_accumulate = {};

function accumulateServerYMD(data) {
    const ymd_name = data.ymd;
    const runs = Object.entries(data.runs);
    const project_name = data.project;
    const source = data.source;
    const total = data.total;

    const key = source + "." + project_name + "." + ymd_name


    acc_data = window.server_accumulate[key]


    if (acc_data == null) {
        acc_data = data;
        acc_data.found = 1;
    } else {
        acc_data.found += 1;

        for ([run_name, run_entry] of runs) {
            acc_data.runs[run_name] = run_entry;
        };
    }
    window.server_accumulate[key] = acc_data;

    // console.log(data, acc_data.found)

    // console.log(acc_data.found)
    if (total == acc_data.found) {
        processServerYMD(acc_data);
        window.server_accumulate[key] = null;
    }

}

/*
 data = {"stats" -> "project" -> "ymd_name" -> "runs" -> []
          "ymd": str(),
          "runs": runs,
          "project": str(),
  }
*/
function processServerYMD(data) {

    //console.log(data);
    const ymd_name = data.ymd;
    const runs = Object.entries(data.runs);
    const project_name = data.project;
    const source = data.source;

    const tab_name = data.tab;
    const ymd_div = document.getElementById(tab_name);
    ymd_div.innerHTML = "";

    const run_dl = document.createElement("dl");
    ymd_div.appendChild(run_dl);

    //runs = Object.entries(projects[ymd_name]);
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


        stats = data.stats[project_name][ymd_name][run_name];
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
        run_dt.innerHTML = "Run Name: " + run_name;
        run_dl.appendChild(run_dt);
        const run_dd = document.createElement("dd");
        run_dl.appendChild(run_dd);


        let header_names = ["Robot", "Site", "Date", "Basename", "Path", "Size", "Status"]
        if (window.has_remotes) {
            header_names = ["Select", "Robot", "Site", "Date", "Basename", "Path", "Size", "Status"]
        }

        const item_names = ["robot_name", "site", "datetime", "basename", "localpath", "hsize"]

        // const header_names = ["Select", "Site", "Date", "Run", "Basename", "Size", "ID", "Status"]
        // const item_names = ["site", "datetime", "run_name", "basename", "hsize", "upload_id"]


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

        run_entry = Object.entries(run_entry);
        run_entry.sort((a, b) => a[0].localeCompare(b[0]));

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

                if (window.has_remotes) {
                    const tdCheckbox = document.createElement("td");
                    const checkbox = document.createElement("input");

                    checkbox.dataset.source = source;
                    checkbox.dataset.datetime = detail.datetime;
                    checkbox.dataset.size = detail.size;
                    checkbox.dataset.group = "table";
                    checkbox.dataset.on_local = detail.on_local;
                    checkbox.dataset.on_remote = detail.on_remote;
                    checkbox.dataset.upload_id = detail.upload_id

                    checkbox.type = "checkbox";
                    checkbox.id = "server_select_" + detail.upload_id
                    tdCheckbox.appendChild(checkbox);
                    tr.appendChild(tdCheckbox);
                }

                item_names.forEach((key) => {
                    const td = document.createElement("td");
                    td.innerHTML = detail[key];

                    if (key == "localpath") {
                        td.innerHTML = "";
                        const icon = document.createElement("i")
                        icon.className = "bi bi-copy"
                        icon.title = "Copy to clipboard: " + detail.localpath;
                        icon.dataset.localpath = detail.localpath;
                        icon.setAttribute("data-bs-toggle", "tooltip");

                        icon.addEventListener('click', function () {
                            const localpath = $(this)[0].dataset.localpath;
                            navigator.clipboard.writeText(localpath);
                        })

                        td.appendChild(icon)


                        const download = document.createElement("i")
                        download.className = "bi bi-download"
                        download.title = "Download "
                        download.id = `download_${detail.upload_id}`;
                        download.dataset.upload_id = detail.upload_id;
                        download.dataset.basename = detail.basename;
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
                    }

                    if (key == "basename") {
                        let topics = null;
                        if (detail.topics) {
                            topics = Object.entries(detail.topics)
                        }

                        if (topics && topics.length > 0) {

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
                            topics.sort((a, b) => a[0].localeCompare(b[0]));
                            for (const [topic, topic_count] of topics) {
                                let dil = document.createElement("li");
                                dul.appendChild(dil);
                                dil.innerHTML = topic + " : (" + topic_count + ")";
                                dil.className = "dropdown-item";
                            }

                        }

                    }

                    tr.appendChild(td);
                });

                const tdStatus = document.createElement("td");
                const statusDiv = document.createElement("div");
                statusDiv.id = `status_${detail.upload_id}`;
                statusDiv.className = "status-div";

                const onLocal = document.createElement("i")
                onLocal.className = "bi bi-server";
                onLocal.title = "On Local";
                onLocal.id = `on_local_${detail.upload_id}`;
                onLocal.setAttribute("data-bs-toggle", "tooltip");
                if (!detail.on_local) {
                    onLocal.title = "Not On Local Server";
                    onLocal.classList.add("grayed-out");
                }
                statusDiv.appendChild(onLocal);

                if (window.has_remotes) {
                    const onRemote = document.createElement("i")
                    onRemote.className = "bi bi-cloud";
                    onRemote.classList.add("remote_icon")
                    onRemote.title = "On Remote";
                    onRemote.id = `on_remote_${detail.upload_id}`;
                    onRemote.setAttribute("data-bs-toggle", "tooltip");
                    if (!detail.on_remote) {
                        onRemote.title = "Not On Remote Server";
                        onRemote.classList.add("grayed-out");
                    }
                    statusDiv.appendChild(onRemote);
                }


                tdStatus.appendChild(statusDiv);
                tr.appendChild(tdStatus);
            });

        }
    };

}

function updateServerData(data) {
    const containerFsInfo = document.getElementById("server-fs-info-container");
    containerFsInfo.innerHTML = ""; // clear previous data

    const ul = document.createElement("ul");
    containerFsInfo.appendChild(ul);

    $.each(data.fs_info, function (_, info) {
        const li = document.createElement("li");
        li.innerHTML = `${info[0]} : <b>${info[1]}%</b> free`;
        ul.appendChild(li);
    });

    const containerData = document.getElementById("server-data-container");
    containerData.innerHTML = ""; // clear previous data

    const source = data.source;

    const server_display_name = document.getElementById("server_source_name");
    server_display_name.innerHTML = source;


    let remote_servers = data.remotes;
    window.has_remotes = remote_servers.length > 0
    if (window.has_remotes) {
        const selectElement = document.createElement("select");
        remote_servers.forEach(server => {
            const optionElement = document.createElement("option");
            optionElement.value = server;
            optionElement.textContent = server;
            selectElement.appendChild(optionElement);
        });

        const linkButton = document.createElement("button");
        linkButton.className = "btn btn-primary";
        linkButton.id = "link_button";
        linkButton.dataset.connected = data.remote_connected
        if (data.remote_connected) {
            linkButton.textContent = "Disconnect";
            msg = { "session_token": window.session_token }
            socket.emit("server_refresh");

        } else {
            linkButton.textContent = "Connect";
        }
        linkButton.addEventListener('click', () => {
            if (linkButton.dataset.connected == "true") {
                console.log("Try to disconnect")
                msg = { "session_token": window.session_token }
                socket.emit("server_disconnect", msg)
            } else {
                const selectOption = selectElement.value;
                console.log("Try to connect to ", selectOption)
                socket.emit("server_connect", { "address": selectOption })
            }
        });

        const refreshButton = document.createElement("button")
        refreshButton.className = "btn btn-secondary";
        refreshButton.id = "refresh_button";
        refreshButton.textContent = "Refresh";
        refreshButton.disabled = !data.remote_connected;
        refreshButton.addEventListener('click', () => {
            msg = { "session_token": window.session_token }
            socket.emit("server_refresh");
        })

        const spanSyncStatus = document.createElement("span");
        const icon = document.createElement("i")
        icon.id = "sync_status";

        icon.setAttribute("data-bs-toggle", "tooltip");
        if (data.remote_connected) {
            icon.className = "bi bi-cloud-fill";
            icon.title = "Connected";
        } else {
            icon.className = "bi bi-cloud";
            icon.classList.add("grayed-out");
            icon.title = "Disconnected";
        }
        spanSyncStatus.appendChild(icon);


        containerData.appendChild(spanSyncStatus);
        containerData.appendChild(selectElement);
        containerData.appendChild(linkButton);
        containerData.appendChild(refreshButton)


    }


    const project_names = Object.keys(data.entries).sort();
    const project_tabs = create_tabs(project_names, containerData, "server");

    $.each(project_tabs, function (project_name, project_tab) {

        // create to level global buttons 
        if (window.has_remotes) {
            const div = document.createElement("div");
            project_tab.append(div)

            div.className = 'btn-group';

            const selectAllButton = document.createElement('button');
            selectAllButton.type = 'button';
            selectAllButton.className = 'btn btn-primary';
            selectAllButton.classList.add("server_button");
            selectAllButton.disabled = !data.remote_connected;
            selectAllButton.id = `select-new-${source}-${project_name}`;
            selectAllButton.dataset.source = source;
            selectAllButton.dataset.project = project_name;
            selectAllButton.onclick = processServerSelectAllNew;
            selectAllButton.textContent = 'Select All New';
            div.appendChild(selectAllButton);

            const clearSelectionsButton = document.createElement('button');
            clearSelectionsButton.type = 'button';
            clearSelectionsButton.className = 'btn btn-secondary';
            clearSelectionsButton.classList.add("server_button");
            clearSelectionsButton.disabled = !data.remote_connected;
            clearSelectionsButton.id = `clear-all-${source}-${project_name}`;
            clearSelectionsButton.dataset.source = source;
            clearSelectionsButton.dataset.project = project_name;
            clearSelectionsButton.onclick = processClearSelections;
            clearSelectionsButton.textContent = 'Clear Selections';
            div.appendChild(clearSelectionsButton);

            const transferSelectedButton = document.createElement('button');
            transferSelectedButton.type = 'button';
            transferSelectedButton.className = 'btn btn-success';
            transferSelectedButton.classList.add("server_button");
            transferSelectedButton.disabled = !data.remote_connected;
            transferSelectedButton.id = `transfer-selected-${source}-${project_name}`;
            transferSelectedButton.dataset.source = source;
            transferSelectedButton.dataset.project = project_name;
            transferSelectedButton.onclick = processServerTransferSelections;
            transferSelectedButton.textContent = 'Push Selected';
            div.appendChild(transferSelectedButton);

            const cancelTransferButton = document.createElement('button');
            cancelTransferButton.type = 'button';
            cancelTransferButton.className = 'btn btn-danger';
            cancelTransferButton.classList.add("server_button");
            cancelTransferButton.disabled = !data.remote_connected;
            cancelTransferButton.id = `cancel-${source}-${project_name}`;
            cancelTransferButton.dataset.source = source;
            cancelTransferButton.dataset.project = project_name;
            cancelTransferButton.onclick = processServerCancelTransfer;
            cancelTransferButton.textContent = 'Stop Push';
            div.appendChild(cancelTransferButton);


        }

        const projects = data.entries[project_name];
        ymd_names = Object.keys(projects).sort()

        const ymd_tabs = create_tabs(ymd_names, project_tab, "server:" + project_name, "request_server_ymd_data");

        $.each(ymd_tabs, function (_, ymd_div) {

            add_placeholder(ymd_div);

        })

    });

}
