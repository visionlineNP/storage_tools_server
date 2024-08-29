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


function processNodeYMD(data)
{
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

            // const headers = ["Select", "Site", "Date", "Run", "Basename", "Size", "Status"];
            const headers = [ "Site", "Date", "Run", "Basename", "Size", "Status"];
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
                onRemote.className = "bi bi-cloud-filled";
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


function updateNodeData(data)
{
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

        // add_placeholder(containerData)
    // const entries = Object.entries(data.entries.entries);
    // entries.sort((a, b) => a[0].localeCompare(b[0]));

    const source_names = Object.keys(data.entries).sort();
    
    const source_tabs = create_tabs(source_names, containerData, "node");
    $.each(source_tabs, function(source_name, source_tab) {
        const source_data = data.entries[source_name];
        console.log(source_name, source_data);
        const project_names = Object.keys(source_data.entries);
        const project_tabs = create_tabs(project_names, source_tab, "node:" + source_name );
        $.each(project_tabs, function(project_name, project_tab) {

            const project_data = source_data.entries[project_name];

            const ymd_names = Object.keys(project_data).sort()
            const ymd_tabs = create_tabs(ymd_names, project_tab, "node:" + source_name  + ":" + project_name, "request_node_ymd_data");
            $.each(ymd_tabs, function(_, ymd_tab) {
                add_placeholder(ymd_tab);
            })
            
        });
    })

    return 


    const project_names = Object.keys(data.entries.entries).sort();
    const project_tabs = create_tabs(project_names, containerData, "node");

    $.each(project_tabs, function (project_name, project_tab) {

        const projects = data.entries[project_name];
        ymd_names = Object.keys(projects).sort()

        const ymd_tabs = create_tabs(ymd_names, project_tab, "node:" + project_name, "request_node_ymd_data");

        $.each(ymd_tabs, function (ymd_name, ymd_div) {

            const p = document.createElement("p");
            p.className = "placeholder-glow";
            p.setAttribute("aria-hidden", "true");
            ymd_div.appendChild(p);
            const sizes = [7,4, 2, 8, 4,4,6,9];
            $.each(sizes, function(_, sz) {
                const span = document.createElement("span");
                p.appendChild(span);
                span.className = "placeholder col-" + sz;

                const space = document.createElement("span");
                p.append(space);
                space.textContent = " ";
            });
        });                 
    });



}

function updateNodeData_old(data) {
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

    entries = data.entries;
    if (entries == null) {
        return;
    }

    entries = Object.entries(entries);
    entries.sort((a, b) => a[0].localeCompare(b[0]));


    const source_tablist = document.createElement("ul");
    source_tablist.className = "nav nav-tabs";
    source_tablist.role = "tablist"
    containerData.appendChild(source_tablist)

    // create the tab menus per source
    let first_source = true;
    for (const [source_name, sources] of entries) {
        console.log(source_name, sources);

        let li = document.createElement("li");
        li.className = "nav-item";
        li.role = "presentation";
        let link = document.createElement("a");
        li.appendChild(link);

        link.innerHTML = source_name;
        source_tablist.appendChild(li)

        if (first_source) {
            link.className = "nav-link active";
            link.setAttribute("aria-selected", "true")
            first_source = false;
        } else {
            link.className = "nav-link";
        }
        link.setAttribute("data-bs-toggle", "tab");
        link.setAttribute("data-bs-target", "#node-" + source_name);
        link.type = "button";
        link.role = "tab";
        link.setAttribute("aria-controls", "node-" + source_name);
    }

    // create the individual tabs per source 
    const sources_div = document.createElement("div");
    sources_div.className = "tab-content";

    containerData.appendChild(sources_div);

    first_source = true;
    for ([source_name, sources] of entries) {
        let source_div = document.createElement("div");
        sources_div.appendChild(source_div);
        if (first_source) {
            source_div.className = "tab-pane fade show active";
            first_source = false;
        } else {
            source_div.className = "tab-pane fade hidden ";
        }
        source_div.id = "node-" + source_div;
        source_div.role = "tabpanel";
        source_div.setAttribute("aria-labelledby", "node-" + source_div);
        source_div.tabIndex = "0";

        sources_stats = sources.stats;
        console.log(sources_stats);

        let btn_group = document.createElement("div");
        btn_group.className = "btn-group";
        source_div.appendChild(btn_group);
        let select_new = document.createElement("button");
        select_new.className = "btn btn-primary";
        select_new.dataset.source = source_name;
        select_new.textContent = "Select New";
        select_new.onclick = select_new_by_source;
        btn_group.appendChild(select_new);

        let send_files = document.createElement("button");
        send_files.className = "btn btn-secondary";
        send_files.dataset.source = source_name;
        send_files.textContent = "Sync Files";
        send_files.onclick = sync_files_by_source;
        btn_group.appendChild(send_files);

        source_items = Object.entries(sources.entries);
        source_items.sort((a, b) => a[0].localeCompare(b[0]));

        const node_tablist = document.createElement("ul");
        node_tablist.className = "nav nav-tabs";
        node_tablist.role = "tablist"
        source_div.appendChild(node_tablist)

        let first_project = true;
        for ([project_name, projects] of source_items) {
            let li = document.createElement("li");
            li.className = "nav-item";
            li.role = "presentation";
            let link = document.createElement("a");
            li.appendChild(link);

            link.innerHTML = project_name;
            node_tablist.appendChild(li)

            if (first_project) {
                link.className = "nav-link active";
                link.setAttribute("aria-selected", "true")
                first_project = false;
            } else {
                link.className = "nav-link";
            }
            link.setAttribute("data-bs-toggle", "tab");
            link.setAttribute("data-bs-target", "#node-" + source_name + "-" + project_name);
            link.type = "button";
            link.role = "tab";
            link.setAttribute("aria-controls", "node-" + source_name + "-" + project_name);
        }

        const projects_div = document.createElement("div");
        projects_div.className = "tab-content";

        source_div.appendChild(projects_div)

        first_project = true;
        for ([project_name, projects] of source_items) {
            let project_div = document.createElement("div");
            projects_div.appendChild(project_div);
            if (first_project) {
                project_div.className = "tab-pane fade show active";
                first_project = false;
            } else {
                project_div.className = "tab-pane fade hidden ";
            }
            project_div.id = "node-" + source_name + "-" + project_name;
            project_div.role = "tabpanel";
            project_div.setAttribute("aria-labelledby", "node-" + source_name + "-" + project_name);
            project_div.tabIndex = "0";

            projects = Object.entries(projects);
            projects.sort((a, b) => a[0].localeCompare(b[0]));

            const ymd_tablist = document.createElement("ul");
            ymd_tablist.className = "nav nav-tabs";
            ymd_tablist.role = "tablist"
            project_div.appendChild(ymd_tablist)

            let first_ymd = true;
            for ([ymd, runs] of projects) {
                let li = document.createElement("li");
                li.className = "nav-item";
                li.role = "presentation";
                let link = document.createElement("a");
                li.appendChild(link);

                link.innerHTML = ymd;
                ymd_tablist.appendChild(li)

                if (first_ymd) {
                    link.className = "nav-link active";
                    link.setAttribute("aria-selected", "true")
                    first_ymd = false;
                } else {
                    link.className = "nav-link";
                }
                link.setAttribute("data-bs-toggle", "tab");
                link.setAttribute("data-bs-target", "#node-" + source_name + "-" + project_name + "-" + ymd);
                link.type = "button";
                link.role = "tab";
                link.setAttribute("aria-controls", "node-" + source_name + "-" + project_name + "-" + ymd);
            }

            const ymds_div = document.createElement("div");
            ymds_div.className = "tab-content";
            project_div.appendChild(ymds_div);
            first_ymd = true;
            for ([ymd, runs] of projects) {

                let ymd_div = document.createElement("div");
                ymds_div.appendChild(ymd_div);
                if (first_ymd) {
                    ymd_div.className = "tab-pane fade show active";
                    first_ymd = false;
                } else {
                    ymd_div.className = "tab-pane fade hidden";
                }
                ymd_div.id = "node-" + project_name + "-" + ymd;
                ymd_div.role = "tabpanel";
                ymd_div.setAttribute("aria-labelledby", "node-" + source_name + "-" + project_name + "-" + ymd);
                ymd_div.tabIndex = "0";

                const run_dl = document.createElement("dl");
                ymd_div.appendChild(run_dl);

                runs = Object.entries(runs);
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

                    stats = sources_stats[project_name][ymd][run_name];
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

                        ["Select", "Site", "Date", "Run", "Basename", "Size", "Status"].forEach((header) => {
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

                            const tdCheckbox = document.createElement("td");
                            const checkbox = document.createElement("input");
                            checkbox.dataset.on_local = detail.on_local;
                            checkbox.dataset.on_remote = detail.on_remote;
                            checkbox.dataset.upload_id = detail.upload_id;
                            checkbox.dataset.source = source_name;
                            checkbox.dataset.page = "node";
                            checkbox.type = "checkbox";
                            checkbox.id = "node_select_" + detail.upload_id
                            tdCheckbox.appendChild(checkbox);
                            tr.appendChild(tdCheckbox);

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
                            onRemote.className = "bi bi-cloud";
                            onRemote.title = "On Remote";
                            onRemote.id = `node_on_remote_${detail.upload_id}`;
                            onRemote.setAttribute("data-bs-toggle", "tooltip");
                            if (!detail.on_remote) {
                                onRemote.title = "Not On Remote Server";
                                onRemote.classList.add("grayed-out");
                            }
                            statusDiv.appendChild(onRemote);


                            tdStatus.appendChild(statusDiv);
                            tr.appendChild(tdStatus);
                        });
                    };
                };
            }

        }

    }
}

function updateNodeData_old_2(data) {
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

    entries = data.entries;
    if (entries == null) {
        return;
    }

    entries = Object.entries(entries);
    entries.sort((a, b) => a[0].localeCompare(b[0]));


    const source_tablist = document.createElement("ul");
    source_tablist.className = "nav nav-tabs";
    source_tablist.role = "tablist"
    containerData.appendChild(source_tablist)

    let first_source = true;
    for (const [source_name, sources] of entries) {
        let li = document.createElement("li");
        li.className = "nav-item";
        li.role = "presentation";
        let link = document.createElement("a");
        li.appendChild(link);

        link.innerHTML = source_name;
        source_tablist.appendChild(li)

        if (first_source) {
            link.className = "nav-link active";
            link.setAttribute("aria-selected", "true")
            first_source = false;
        } else {
            link.className = "nav-link";
        }
        link.setAttribute("data-bs-toggle", "tab");
        link.setAttribute("data-bs-target", "#node-" + source_name);
        link.type = "button";
        link.role = "tab";
        link.setAttribute("aria-controls", "node-" + source_name);
    }

    const sources_div = document.createElement("div");
    sources_div.className = "tab-content";

    containerData.appendChild(sources_div)

    first_source = true;
    for ([source_name, sources] of entries) {
        let source_div = document.createElement("div");
        sources_div.appendChild(source_div);
        if (first_source) {
            source_div.className = "tab-pane fade show active";
            first_source = false;
        } else {
            source_div.className = "tab-pane fade hidden ";
        }
        source_div.id = "node-" + source_div;
        source_div.role = "tabpanel";
        source_div.setAttribute("aria-labelledby", "node-" + source_div);
        source_div.tabIndex = "0";

        // stats = sources.stats;
        sources = Object.entries(sources.entries);
        sources.sort((a, b) => a[0].localeCompare(b[0]));


        const node_tablist = document.createElement("ul");
        node_tablist.className = "nav nav-tabs";
        node_tablist.role = "tablist"
        source_div.appendChild(node_tablist)

        let first_project = true;
        for ([project_name, projects] of entries) {
            let li = document.createElement("li");
            li.className = "nav-item";
            li.role = "presentation";
            let link = document.createElement("a");
            li.appendChild(link);

            link.innerHTML = project_name;
            node_tablist.appendChild(li)

            if (first_project) {
                link.className = "nav-link active";
                link.setAttribute("aria-selected", "true")
                first_project = false;
            } else {
                link.className = "nav-link";
            }
            link.setAttribute("data-bs-toggle", "tab");
            link.setAttribute("data-bs-target", "#node-" + source_name + "-" + project_name);
            link.type = "button";
            link.role = "tab";
            link.setAttribute("aria-controls", "node-" + source_name + "-" + project_name);
        }

        const projects_div = document.createElement("div");
        projects_div.className = "tab-content";

        source_div.appendChild(projects_div)

        first_project = true;
        for ([project_name, projects] of entries) {
            let project_div = document.createElement("div");
            projects_div.appendChild(project_div);
            if (first_project) {
                project_div.className = "tab-pane fade show active";
                first_project = false;
            } else {
                project_div.className = "tab-pane fade hidden ";
            }
            project_div.id = "node-" + project_name;
            project_div.role = "tabpanel";
            project_div.setAttribute("aria-labelledby", "node-" + source_name + "-" + project_name);
            project_div.tabIndex = "0";

            projects = Object.entries(projects);
            projects.sort((a, b) => a[0].localeCompare(b[0]));

            const ymd_tablist = document.createElement("ul");
            ymd_tablist.className = "nav nav-tabs";
            ymd_tablist.role = "tablist"
            project_div.appendChild(ymd_tablist)

            let first_ymd = true;
            for ([ymd, runs] of projects) {
                let li = document.createElement("li");
                li.className = "nav-item";
                li.role = "presentation";
                let link = document.createElement("a");
                li.appendChild(link);

                link.innerHTML = ymd;
                ymd_tablist.appendChild(li)

                if (first_ymd) {
                    link.className = "nav-link active";
                    link.setAttribute("aria-selected", "true")
                    first_ymd = false;
                } else {
                    link.className = "nav-link";
                }
                link.setAttribute("data-bs-toggle", "tab");
                link.setAttribute("data-bs-target", "#node-" + source_name + "-" + project_name + "-" + ymd);
                link.type = "button";
                link.role = "tab";
                link.setAttribute("aria-controls", "node-" + source_name + "-" + project_name + "-" + ymd);
            }

            const ymds_div = document.createElement("div");
            ymds_div.className = "tab-content";
            project_div.appendChild(ymds_div);
            first_ymd = true;
            for ([ymd, runs] of projects) {

                let ymd_div = document.createElement("div");
                ymds_div.appendChild(ymd_div);
                if (first_ymd) {
                    ymd_div.className = "tab-pane fade show active";
                    first_ymd = false;
                } else {
                    ymd_div.className = "tab-pane fade hidden";
                }
                ymd_div.id = "node-" + project_name + "-" + ymd;
                ymd_div.role = "tabpanel";
                ymd_div.setAttribute("aria-labelledby", "node-" + source_name + "-" + project_name + "-" + ymd);
                ymd_div.tabIndex = "0";

                const run_dl = document.createElement("dl");
                ymd_div.appendChild(run_dl);

                runs = Object.entries(runs);
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


                    stats = data.stats[project_name][ymd][run_name];
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

                        ["Select", "Site", "Date", "Run", "Basename", "Size", "Status"].forEach((header) => {
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

                            const tdCheckbox = document.createElement("td");
                            const checkbox = document.createElement("input");
                            checkbox.type = "checkbox";
                            checkbox.id = "node_select_" + detail.upload_id
                            tdCheckbox.appendChild(checkbox);
                            tr.appendChild(tdCheckbox);

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
                            onRemote.className = "bi bi-cloud";
                            onRemote.title = "On Remote";
                            onRemote.id = `node_on_remote_${detail.upload_id}`;
                            onRemote.setAttribute("data-bs-toggle", "tooltip");
                            if (!detail.on_remote) {
                                onRemote.title = "Not On Remote Server";
                                onRemote.classList.add("grayed-out");
                            }
                            statusDiv.appendChild(onRemote);


                            tdStatus.appendChild(statusDiv);
                            tr.appendChild(tdStatus);
                        });
                    };
                };
            }

        }
    }

}