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

        const header_names = ["Site", "Robot", "Date", "Basename", "Size", "Status"]
        const item_names = ["site", "robot_name" , "datetime", "basename", "hsize"]

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

        continue;

        for ([relpath, items] of run_entry) {
            const relpath_tag = document.createElement("span");
            relpath_tag.innerHTML = relpath;
            run_dd.appendChild(relpath_tag);

            const table = document.createElement("table");
            table.className = "table table-striped";
            run_dd.appendChild(table);

            const thead = document.createElement("thead");
            table.appendChild(thead);
            const tr = document.createElement("tr");
            thead.appendChild(tr);

            // const headers = ["Select", "Site", "Date", "Basename", "Size", "Status"];
            const headers = ["Site", "Date", "Basename", "Size", "Status"];
            headers.forEach((header) => {
                const th = document.createElement("th");
                th.textContent = header;
                tr.appendChild(th);
            });

            const tbody = document.createElement("tbody");
            table.appendChild(tbody);

            items.sort((a, b) => a["datetime"].localeCompare(b["datetime"]))

            $.each(items, function (_, detail) {
                const tr = document.createElement("tr");
                tbody.appendChild(tr);

                // const tdCheckbox = document.createElement("td");
                // const checkbox = document.createElement("input");
                // checkbox.dataset.on_local = detail.on_local;
                // checkbox.dataset.on_remote = detail.on_remote;
                // checkbox.dataset.upload_id = detail.upload_id;
                // checkbox.dataset.source = source_name;
                // checkbox.dataset.page = "node";
                // checkbox.type = "checkbox";
                // checkbox.id = "node_select_" + detail.upload_id
                // tdCheckbox.appendChild(checkbox);
                // tr.appendChild(tdCheckbox);

                ["site", "datetime", "run_name", "basename", "hsize"].forEach((key) => {
                    const td = document.createElement("td");
                    td.innerHTML = detail[key];

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

                    tr.appendChild(td);
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
        };
    };

}


function updateNodeData(data) {
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

    const source_tabs = create_tabs(source_names, containerData, "node");
    $.each(source_tabs, function (source_name, source_tab) {
        const source_data = data.entries[source_name];
        console.log(source_name, source_data);
        const project_names = Object.keys(source_data);
        const project_tabs = create_tabs(project_names, source_tab, "node:" + source_name);
        $.each(project_tabs, function (project_name, project_tab) {

            const project_data = source_data[project_name];

            const ymd_names = Object.keys(project_data).sort()
            const ymd_tabs = create_tabs(ymd_names, project_tab, "node:" + source_name + ":" + project_name, "request_node_ymd_data");
            $.each(ymd_tabs, function (_, ymd_tab) {
                add_placeholder(ymd_tab);
            })

        });
    })

}

