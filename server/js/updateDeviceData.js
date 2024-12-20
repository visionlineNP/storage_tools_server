
function processClearSelectionsByDate() {
  const source = $(this)[0].dataset.source;
  const date = $(this)[0].dataset.date;

  $('input[type="checkbox"][data-group="table"][data-source="' + source + '"][data-date="' + date + '"]:checked').prop('checked', false);
  updateDeviceSelectCounts(source);

}

function processClearSelections() {
  const source = $(this)[0].dataset.source;

  $('input[type="checkbox"][data-group="table"][data-source="' + source + '"]:checked').prop('checked', false);
  updateDeviceSelectCounts(source);
}


function processCancelTransfer() {
  const source = $(this)[0].dataset.source;
  //console.log($(this));
  cancelTransfers(source);
}

function processRemoveSelectedByDate() {
  const source = $(this)[0].dataset.source;
  const date = $(this)[0].dataset.date;

  let selectedUpdateIds = [];
  $('input[type="checkbox"][data-group="table"][data-source="' + source + '"][data-date="' + date + '"][data-on-server="true"][data-on-device="true"]').each(function () {
    selectedUpdateIds.push($(this).attr('id'));
  });
  //console.log(selectedUpdateIds, source);
  removeFiles(selectedUpdateIds);

}

function processRemoveSelected() {
  const source = $(this)[0].dataset.source;

  let selectedUpdateIds = [];
  $('input[type="checkbox"][data-group="table"][data-source="' + source + '"][data-on-server="true"][data-on-device="true"]').each(function () {
    selectedUpdateIds.push($(this).attr('id'));
  });
  //console.log(selectedUpdateIds, source);
  removeFiles(selectedUpdateIds, source);

}


function processRescanSource() {
  const source = $(this)[0].dataset.source;
  rescanSource(source);
}

function processSelectAllNewByDate() {
  const source = $(this)[0].dataset.source;
  const date = $(this)[0].dataset.date;
  //console.log(source, date);

  $('input[type="checkbox"][data-group="table"][data-source="' + source + '"][data-date="' + date + '"][data-on-device="true"][data-on-server="false"]').prop('checked', true);
  updateDeviceSelectCounts(source);

}

function processSelectAllNew() {
  const source = $(this)[0].dataset.source;
  $('input[type="checkbox"][data-group="table"][data-source="' + source + '"][data-on-device="true"][data-on-server="false"]').prop('checked', true);
  updateDeviceSelectCounts(source);

}



function processTransferSelectionsByDate() {
  const source = $(this)[0].dataset.source;
  const date = $(this)[0].dataset.date;

  let selectedUpdateIds = [];
  $('input[type="checkbox"][data-group="table"][data-source="' + source + '"][data-date="' + date + '"]:checked').each(function () {
    selectedUpdateIds.push($(this).attr('id'));
  });
  //console.log(selectedUpdateIds, source);
  transferFiles(selectedUpdateIds, source);
}


function processTransferSelections() {
  const source = $(this)[0].dataset.source;

  let selectedUpdateIds = [];
  $('input[type="checkbox"][data-group="table"][data-source="' + source + '"]:checked').each(function () {
    selectedUpdateIds.push($(this).attr('id'));
  });
  //console.log(selectedUpdateIds, source);
  transferFiles(selectedUpdateIds, source);
}


function updateDeviceData(data) {
  // save device data for later.  
  // console.log(data);

  window.device_data = {};

  let valid = true
  $.each(data, function (source_name, source_item) {
    //console.log(source_name, source_item)
    if (source_item.project && source_item.stats == null) {
      console.log(source_name + " is invalid")
      valid = false;
    }
  });
  if (!valid) {
    return;
  }

  const container = document.getElementById("device-data-container");

  container.innerHTML = "";

  if (Object.keys(data).length == 0) {
    updateDeviceCount(0);
    return;
  }

  source_names = Object.keys(data).sort();

  source_tabs = create_tabs(source_names, container, "devices");

  // save the source tabs to allow for easy updating. 
  window.source_tabs = source_tabs;

  //console.log("length is ", source_names.length);
  updateDeviceCount(source_names.length);

  $.each(source_tabs, function (source_name, source_tab) {
    const source_item = data[source_name];

    //console.log(source_item)

    window.device_data[source_name] = {};
    const project = source_item.project;

    const header = document.createElement("div");
    source_tab.appendChild(header);

    // console.log(project)

    // handle case where device does not have project set. 
    if (project == null) {
      let sourceHTML= "<H2> Missing Information! </h2><p> Verify that";
      sourceHTML += "<ul><li>On Device: <b>Project Name</b> is set</li>";
      sourceHTML += "<li>On Server:Configure:Projects, that the <b>Project</b> is listed and has a <B>Volume</b></li> "
      sourceHTML += "</ul><p>When that is done, press the [Refresh] button"

      header.innerHTML = sourceHTML;

      const refreshButton = document.createElement('button');
      refreshButton.type = "button"
      refreshButton.className = 'btn btn-info';
      refreshButton.textContent = 'Refresh';
      refreshButton.dataset.source = source_name

      refreshButton.addEventListener("click",(event) => {
        const source = event.target.dataset.source;
         rescanSource(source);
      })
      container.append(refreshButton)

      return;
    }

    // project should be set by here. 

    let sourceHtml = '<h2>' + project + ' </h2>';
    header.innerHTML = sourceHtml;

    let fs_info_list = document.createElement("ul");
    header.appendChild(fs_info_list);

    $.each(source_item.fs_info, function (_, info) {
      let listItem = document.createElement("li");
      listItem.innerHTML = `${info[0]} : <b>${info[1]}%</b> free`;
      fs_info_list.appendChild(listItem);
    });


    // console.log(source_item);

    updateDeviceStats(source_name, source_item.stats["total"]);

    // create to level global buttons 
    {
      const div = document.createElement("div");
      source_tab.append(div)

      div.className = 'btn-group';

      const selectAllButton = document.createElement('button');
      selectAllButton.type = 'button';
      selectAllButton.className = 'btn btn-primary';
      selectAllButton.id = `select-new-${source_name}`;
      selectAllButton.dataset.source = source_name;
      selectAllButton.onclick = processSelectAllNew;
      selectAllButton.textContent = 'Select All New';
      div.appendChild(selectAllButton);

      const clearSelectionsButton = document.createElement('button');
      clearSelectionsButton.type = 'button';
      clearSelectionsButton.className = 'btn btn-secondary';
      clearSelectionsButton.id = `clear-all-${source_name}`;
      clearSelectionsButton.dataset.source = source_name;
      clearSelectionsButton.onclick = processClearSelections;
      clearSelectionsButton.textContent = 'Clear Selections';
      div.appendChild(clearSelectionsButton);

      const transferSelectedButton = document.createElement('button');
      transferSelectedButton.type = 'button';
      transferSelectedButton.className = 'btn btn-success';
      transferSelectedButton.id = `transfer-selected-${source_name}`;
      transferSelectedButton.dataset.source = source_name;
      transferSelectedButton.onclick = processTransferSelections;
      transferSelectedButton.textContent = 'Pull Selected';
      div.appendChild(transferSelectedButton);

      const cancelTransferButton = document.createElement('button');
      cancelTransferButton.type = 'button';
      cancelTransferButton.className = 'btn btn-danger';
      cancelTransferButton.id = `cancel-${source_name}`;
      cancelTransferButton.dataset.source = source_name;
      cancelTransferButton.onclick = processCancelTransfer;
      cancelTransferButton.textContent = 'Stop Pull';
      div.appendChild(cancelTransferButton);

      const removeSelectedButton = document.createElement('button');
      removeSelectedButton.type = 'button';
      removeSelectedButton.className = 'btn btn-danger';
      removeSelectedButton.id = `remove-selected-${source_name}`;
      removeSelectedButton.dataset.source = source_name;
      removeSelectedButton.onclick = processRemoveSelected;
      removeSelectedButton.textContent = 'Removed Completed';
      div.appendChild(removeSelectedButton);


      const rescanButtonDiv = document.createElement('div');
      rescanButtonDiv.className = 'btn-group';

      const rescanButton = document.createElement('button');
      rescanButton.type = 'button';
      rescanButton.className = 'btn btn-primary';
      rescanButton.id = `rescan-${source_name}`;
      rescanButton.dataset.source = source_name;
      rescanButton.onclick = processRescanSource;
      rescanButton.textContent = 'Scan';
      rescanButtonDiv.appendChild(rescanButton);
      source_tab.append(rescanButtonDiv);

      const buttonBarDiv = document.createElement('div');
      buttonBarDiv.className = 'btn-group';

      const editProjectDropdownDiv = document.createElement('div');
      editProjectDropdownDiv.className = 'dropdown';

      const editProjectButton = document.createElement('button');
      editProjectButton.type = 'button';
      editProjectButton.className = 'btn btn-info dropdown-toggle';
      editProjectButton.dataset.toggle = 'dropdown';
      editProjectButton.ariaHaspopup = true;
      editProjectButton.ariaExpanded = false;
      editProjectButton.textContent = 'Set Project';

      const projectMenuDiv = document.createElement('div');
      projectMenuDiv.className = 'dropdown-menu project-menu';
      projectMenuDiv.dataset.source = source_name;

      editProjectDropdownDiv.appendChild(editProjectButton);
      editProjectDropdownDiv.appendChild(projectMenuDiv);
      source_tab.append(editProjectDropdownDiv)
    }

    ymd_names = Object.keys(source_item.entries).sort();

    const levels = {}
    ymd_names.forEach(ymd => {
        const { ym, day } = splitYMD(ymd);
        if (levels[ym] == null) { levels[ym] = [ymd] }
        else { levels[ym].push(ymd) }
    });

    ym_names = Object.keys(levels).sort()
    const ym_tabs = create_tabs(ym_names, source_tab, "device:" + source_name + ":ym")

    $.each(ym_tabs, function (ym_name, ym_div) {
        const ymd_names = levels[ym_name];
        const ymd_tabs = create_tabs(ymd_names, ym_div, "device:" + source_name, "request_device_ymd_data", true);
        $.each(ymd_tabs, function (_, ymd_div) {
            add_placeholder(ymd_div);
        })
    })    
  });

}

function populateDeviceYMDTab(source_item) {
  // console.log(source_item)

  const date = source_item.ymd
  const ymd_tab = document.getElementById(source_item.tab)
  const source_name = source_item.device_source
  const date_items = source_item.reldir;

  ymd_tab.innerHTML = ""

  let ymd_stats_div = document.createElement("div");
  ymd_stats_div.className = "container";
  ymd_tab.appendChild(ymd_stats_div);

  let stats_row_div = document.createElement("div");
  stats_row_div.className = "row align-items-center";
  ymd_stats_div.appendChild(stats_row_div);
  ymd_stats_col_1 = document.createElement("div");
  ymd_stats_col_1.className = "col";
  stats_row_div.appendChild(ymd_stats_col_1);

  ymd_stats_col_2 = document.createElement("div");
  ymd_stats_col_2.className = "col";
  stats_row_div.appendChild(ymd_stats_col_2);


  stats = source_item.stats[source_name].stats[date];
  // console.log(stats)

  start_time = stats["start_datetime"];
  end_time = stats["end_datetime"];
  duration = stats["hduration"];
  total_size = stats["htotal_size"];


  let stats_ul = document.createElement("ul");
  ymd_stats_col_1.appendChild(stats_ul);

  let li = document.createElement("li");
  li.innerHTML = "<b>Start</b>: " + start_time;
  stats_ul.appendChild(li);

  li = document.createElement("li");
  li.innerHTML = "<b>Duration</b>: " + duration;
  stats_ul.appendChild(li);

  li = document.createElement("li");
  li.innerHTML = "<b>Size</b>: " + total_size;
  stats_ul.appendChild(li);

  let dtable = document.createElement("table");
  dtable.className = "table table-striped";
  ymd_stats_col_2.appendChild(dtable);

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


  {
    const div = document.createElement('div');
    ymd_tab.appendChild(div);
    div.className = 'btn-group';

    const selectAllButton = document.createElement('button');
    selectAllButton.type = 'button';
    selectAllButton.className = 'btn btn-primary';
    selectAllButton.id = `select-new-${source_name}-${date}`;
    selectAllButton.dataset.date = date;
    selectAllButton.dataset.source = source_name;
    selectAllButton.onclick = processSelectAllNewByDate;
    selectAllButton.textContent = 'Select All New by Date';
    div.appendChild(selectAllButton);

    const clearSelectionsButton = document.createElement('button');
    clearSelectionsButton.type = 'button';
    clearSelectionsButton.className = 'btn btn-secondary';
    clearSelectionsButton.id = `clear-all-${source_name}-${date}`;
    clearSelectionsButton.dataset.date = date;
    clearSelectionsButton.dataset.source = source_name;
    clearSelectionsButton.onclick = processClearSelectionsByDate;
    clearSelectionsButton.textContent = 'Clear Selections for Date';
    div.appendChild(clearSelectionsButton);

    const transferSelectedButton = document.createElement('button');
    transferSelectedButton.type = 'button';
    transferSelectedButton.className = 'btn btn-success';
    transferSelectedButton.id = `transfer-selected-${source_name}-${date}`;
    transferSelectedButton.dataset.date = date;
    transferSelectedButton.dataset.source = source_name;
    transferSelectedButton.onclick = processTransferSelectionsByDate;
    transferSelectedButton.textContent = 'Pull Selected for Date';
    div.appendChild(transferSelectedButton);

    // const cancelTransferButton = document.createElement('button');
    // cancelTransferButton.type = 'button';
    // cancelTransferButton.className = 'btn btn-danger';
    // cancelTransferButton.id = `cancel-${source}-${date}`;
    // cancelTransferButton.dataset.source = source;
    // cancelTransferButton.onclick = processCancelTransfer;
    // cancelTransferButton.textContent = 'Stop Transfer';
    // div.appendChild(cancelTransferButton);
    const removeSelectedButton = document.createElement('button');
    removeSelectedButton.type = 'button';
    removeSelectedButton.className = 'btn btn-danger';
    removeSelectedButton.id = `remove-selected-${source_name}-${date}`;
    removeSelectedButton.dataset.date = date;
    removeSelectedButton.dataset.source = source_name;
    removeSelectedButton.onclick = processRemoveSelectedByDate;
    removeSelectedButton.textContent = 'Removed Completed for Date';
    div.appendChild(removeSelectedButton);

    const buttonBarDiv = document.createElement('div');
    buttonBarDiv.className = 'btn-group';
    ymd_tab.appendChild(buttonBarDiv);

    const editRobotDropdownDiv = document.createElement('div');
    editRobotDropdownDiv.className = 'dropdown';

    const editRobotButton = document.createElement('button');
    editRobotButton.type = 'button';
    editRobotButton.className = 'btn btn-info dropdown-toggle';
    editRobotButton.dataset.toggle = 'dropdown';
    editRobotButton.ariaHaspopup = true;
    editRobotButton.ariaExpanded = false;
    editRobotButton.textContent = 'Edit Robot';

    const robotMenuDiv = document.createElement('div');
    robotMenuDiv.className = 'dropdown-menu robot-menu';
    robotMenuDiv.dataset.source = source_name;
    robotMenuDiv.dataset.date = date;


    editRobotDropdownDiv.appendChild(editRobotButton);
    editRobotDropdownDiv.appendChild(robotMenuDiv);

    const editSiteDropdownDiv = document.createElement('div');
    editSiteDropdownDiv.className = 'dropdown';

    const editSiteButton = document.createElement('button');
    editSiteButton.type = 'button';
    editSiteButton.className = 'btn btn-info dropdown-toggle';
    editSiteButton.dataset.toggle = 'dropdown';
    editSiteButton.ariaHaspopup = true;
    editSiteButton.ariaExpanded = false;
    editSiteButton.textContent = 'Edit Site';

    const siteMenuDiv = document.createElement('div');
    siteMenuDiv.className = 'dropdown-menu site-menu';
    siteMenuDiv.dataset.source = source_name;
    siteMenuDiv.dataset.date = date;

    editSiteDropdownDiv.appendChild(editSiteButton);
    editSiteDropdownDiv.appendChild(siteMenuDiv);

    buttonBarDiv.appendChild(editRobotDropdownDiv);
    buttonBarDiv.appendChild(editSiteDropdownDiv);


  }

  const thHeaders = [
    '', 'Robot', 'Site', 'Basename', 'DateTime', 'File size', 'State'
  ];


  const table = document.createElement('table');
  table.className = 'table table-striped';
  ymd_tab.append(table);

  const thead = document.createElement('thead');
  const tr = document.createElement('tr');

  thHeaders.forEach(header => {
    const th = document.createElement('th');
    th.textContent = header;
    tr.appendChild(th);
  });

  thead.appendChild(tr);
  table.appendChild(thead);

  const tbody = document.createElement('tbody');
  table.appendChild(tbody);

  date_entries = Object.entries(date_items);
  date_entries.sort((a, b) => a[0].localeCompare(b[0]));

  date_entries.forEach((data_entry) => {
    relpath = data_entry[0];
    const relpath_entries = data_entry[1];

    const run_header_tr = document.createElement("tr");
    run_header_tr.className = "table-active";
    tbody.appendChild(run_header_tr);

    const run_header_td = document.createElement("td");
    run_header_td.className = "table_relpath";
    run_header_td.setAttribute("colspan", thHeaders.length);
    run_header_tr.appendChild(run_header_td);

    const relpath_tag = document.createElement("span");
    relpath_tag.className = "table_relpath";
    relpath_tag.innerHTML = relpath;
    run_header_td.appendChild(relpath_tag);

    updateDeviceDataEntry(relpath_entries, source_name, date, tbody);

  });

  // Add event listener for the site select elements
  $('.site-select').on('change', function () {
    let source = $(this).data('source');
    let uploadId = $(this).data('upload-id');
    let selectedValue = $(this).val();

    if (selectedValue === 'add-new-site') {
      let newSite = prompt('Enter new site name:');
      if (newSite) {
        // Emit event to add new site
        socket.emit('add_site', { site: newSite, "session_token": window.session_token });
        // Add new site to the global sites array and update all dropdowns
        window.sites.push(newSite);
        updateAllSiteSelects();
        // Set the new site as the selected value
        $(this).val(newSite);
      }
    } else {
      // Emit event to update the site for this entry
      socket.emit('update_entry_site', { source: source, upload_id: uploadId, site: selectedValue, "session_token": window.session_token });
      window.device_data[source][uploadId].site = selectedValue;
    }
  });

  // Add event listener for the robot select elements
  $('.robot-select').on('change', function () {
    let source = $(this).data('source');
    let uploadId = $(this).data('upload-id');
    let selectedValue = $(this).val();

    if (selectedValue === 'add-new-robot') {
      let newRobot = prompt('Enter new robot name:');
      if (newRobot) {
        // Emit event to add new site
        socket.emit('add_robot', { robot: newRobot, "session_token": window.session_token });
        // Add new site to the global sites array and update all dropdowns
        window.robots.push(newRobot);
        updateAllRobotSelects();
        // Set the new site as the selected value
        $(this).val(newRobot);
      }
    } else {
      //console.log({ source: source, upload_id: uploadId, robot: selectedValue })
      // Emit event to update the site for this entry
      socket.emit('update_entry_robot', { source: source, upload_id: uploadId, robot: selectedValue, "session_token": window.session_token });

      // update the local value. 
      window.device_data[source][uploadId].robot_name = selectedValue;

    }

  });

  populateEditMenus();

  $('[data-bs-toggle="tooltip"]').tooltip();

}


function updateDeviceDataEntry(relpath_entries, source_name, date, tbody) {
  // console.log(relpath_entries)
  relpath_entries.sort((a, b) => a.datetime.localeCompare(b.datetime))

  for (const entry of relpath_entries) {

    window.device_data[source_name][entry.upload_id] = entry;

    let siteOptionsHtml = '';
    $.each(window.sites, (_, site) => {
      const selected = site === entry.site ? ' selected' : '';
      siteOptionsHtml += `<option onchange= value="${site}"${selected}>${site}</option>`;
    });
    siteOptionsHtml += '<option value="add-new-site">Add New Site</option>';

    let robotOptionsHtml = '';
    $.each(window.robots, (_, robot) => {
      const selected = robot === entry.robot_name ? ' selected' : '';
      robotOptionsHtml += `<option value="${robot}"${selected}>${robot}</option>`;
    });
    robotOptionsHtml += '<option value="add-new-robot">Add New Robot</option>';

    const tr = document.createElement('tr');

    const tdCheckbox = document.createElement('td');
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.id = entry.upload_id;
    checkbox.dataset.source = source_name;
    checkbox.dataset.date = date;
    checkbox.dataset.group = "table";
    checkbox.dataset.onDevice = entry.on_device;
    checkbox.dataset.onServer = entry.on_server;
    checkbox.dataset.size = entry.size;
    checkbox.addEventListener("change", (event) => {
      const source = event.target.dataset.source;
      updateDeviceSelectCounts(source);
    })
    tdCheckbox.appendChild(checkbox);
    tr.appendChild(tdCheckbox);

    // const tdProject = document.createElement('td');
    // tdProject.textContent = entry.project;
    // tr.appendChild(tdProject);
    const tdRobotSelect = document.createElement('td');
    const robotSelect = document.createElement('select');
    robotSelect.id = `robot_${entry.upload_id}`;
    robotSelect.className = 'robot-select';
    robotSelect.dataset.source = source_name;
    robotSelect.dataset.uploadId = entry.upload_id;
    robotSelect.innerHTML = robotOptionsHtml;
    tdRobotSelect.appendChild(robotSelect);
    tr.appendChild(tdRobotSelect);

    const tdSiteSelect = document.createElement('td');
    const siteSelect = document.createElement('select');
    siteSelect.id = `site_${entry.upload_id}`;
    siteSelect.className = 'site-select';
    siteSelect.dataset.source = source_name;
    siteSelect.dataset.uploadId = entry.upload_id;
    siteSelect.innerHTML = siteOptionsHtml;
    tdSiteSelect.appendChild(siteSelect);
    tr.appendChild(tdSiteSelect);

    const tdBasename = document.createElement('td');
    tdBasename.innerHTML = entry.basename;

    let topics = null;
    if (entry.topics) {
      topics = Object.entries(entry.topics)
    }

    if (topics && topics.length > 0) {

      tdBasename.innerHTML += "&nbsp;";

      let dropdown = document.createElement("div");
      tdBasename.appendChild(dropdown);
      dropdown.className = "dropdown";


      let caret = document.createElement("i");
      caret.className = "fas fa-caret-down dropdown-toggle";
      caret.setAttribute("data-bs-toggle", "dropdown");
      caret.id = "topics-" + entry.upload_id;
      caret.setAttribute("aria-expanded", "false");
      dropdown.appendChild(caret);

      let dul = document.createElement("ul");
      dul.className = "dropdown-menu";
      dul.setAttribute("aria-labelledby", "topics-" + entry.upload_id);
      dropdown.appendChild(dul);

      topics.sort((a, b) => a[0].localeCompare(b[0]));
      for (const [topic, topic_count] of topics) {
        let dil = document.createElement("li");
        dul.appendChild(dil);
        dil.innerHTML = topic + " : (" + topic_count + ")";
        dil.className = "dropdown-item";
      }
    }
    tr.appendChild(tdBasename);

    const tdDateTimeInput = document.createElement('td');
    tdDateTimeInput.innerHTML = entry.datetime;
    // const dateTimeInput = document.createElement('input');
    // dateTimeInput.type = 'datetime-local';
    // dateTimeInput.id = `date_${entry.upload_id}`;
    // dateTimeInput.name = `date_${entry.upload_id}`;
    // dateTimeInput.value = entry.datetime;
    // dateTimeInput.onchange = () => postDateTimeChange(source, entry.upload_id);
    // tdDateTimeInput.appendChild(dateTimeInput);
    tr.appendChild(tdDateTimeInput);

    const tdFileSize = document.createElement('td');
    tdFileSize.textContent = entry.hsize;
    tr.appendChild(tdFileSize);

    const tdStatusDiv = document.createElement('td');
    const statusDiv = document.createElement('div');
    statusDiv.id = `status_${entry.upload_id}`;
    statusDiv.className = 'status-div';
    //statusDiv.textContent = entry.status;
    const onDevice = document.createElement("i");
    onDevice.className = "bi bi-robot";
    onDevice.title = "On Device";
    onDevice.id = `on_device_${entry.upload_id}`;
    onDevice.setAttribute("data-bs-toggle", "tooltip");
    if (!entry.on_device) {
      onDevice.title = "Not On Device";
      onDevice.classList.add("grayed-out");
    }
    statusDiv.appendChild(onDevice);

    const onServer = document.createElement("i");
    onServer.className = "bi bi-server";
    onServer.title = "On Server";
    onServer.id = `on_server_${entry.upload_id}`;
    onServer.setAttribute("data-bs-toggle", "tooltip");
    if (!entry.on_server) {
      onServer.title = "Not On Server";
      onServer.classList.add("grayed-out");
    }
    statusDiv.appendChild(onServer);

    tdStatusDiv.appendChild(statusDiv);
    tr.appendChild(tdStatusDiv);

    tbody.appendChild(tr);
  };
}

function updateDeviceStats(source_name, stats) {
  const source_tab = window.source_tabs[source_name];

  let div = document.getElementById(source_name + "_device_file_stats");

  if (div == null) {
    div = document.createElement("div");
    div.id = source_name + "_device_file_stats";
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

  td.innerHTML = stats["on_server_hsize"] + " / " + stats["htotal_size"];
  drow.appendChild(td);

  for ([_, datatype_entry] of datatypes) {
    let td = document.createElement("td");
    drow.appendChild(td);
    td.innerHTML = datatype_entry["on_server_hsize"] + " / " + datatype_entry["htotal_size"];
  }

  td = document.createElement("td");
  td.id = "device_selected_hsize"
  td.innerHTML = "0 B"
  drow.appendChild(td)

  drow = document.createElement("tr");
  dbody.appendChild(drow);

  td = document.createElement("td");
  td.innerHTML = "<b>Count</b>";
  drow.appendChild(td);

  td = document.createElement("td");
  td.innerHTML = stats["on_server_count"] + " / " + stats["count"];
  drow.appendChild(td);


  for ([_, datatype_entry] of datatypes) {
    let td = document.createElement("td");
    drow.appendChild(td);
    td.innerHTML = datatype_entry["on_server_count"] + " / " + datatype_entry["count"];
  }

  td = document.createElement("td");
  td.id = "device_selected_count"
  td.innerHTML = "0"
  drow.appendChild(td)


}

function updateDeviceSelectCounts(source)
{
  let total_size = 0;
  let total_count = 0;
  $('input[type="checkbox"][data-group="table"][data-source="' + source + '"]:checked').each(function () {
    total_count += 1;
    total_size += parseInt($(this).attr("data-size"));
  });
  let hsize = formatBytes(total_size);
  //console.log(total_count, total_size, hsize)

  let span = document.getElementById("device_selected_hsize")
  if( span ) {
    span.innerHTML = hsize;
  }
  span = document.getElementById("device_selected_count")
  if( span ) {
    span.innerHTML = total_count;
  }
}


window.device_accumulate = {};

function accumulateDeviceYMD(data) {
  //console.log(data)

  const ymd_name = data.ymd;
  const reldirs = Object.entries(data.reldir);
  const device_source = data.device_source;
  const source = data.source;
  const total = data.total;
  const index = data.index;

  const key = source + "." + device_source + "." + ymd_name

  acc_data = window.device_accumulate[key]

  if (acc_data == null) {
    acc_data = data;
    acc_data.found = 1;
  } else {
    acc_data.found += 1;

    for ([rel_dir, entry] of reldirs) {
      // acc_data.reldir[rel_dir] = entry;
      acc_data.reldir[rel_dir] = [...(acc_data.reldir[rel_dir] || []), ...entry];
    };
  }
  window.device_accumulate[key] = acc_data;

  // console.log(data, acc_data.found, total)

  // console.log(acc_data.found)
  if (total == acc_data.found) {
    populateDeviceYMDTab(acc_data);
    window.device_accumulate[key] = null;
  }

}

function updateDeviceCount(count) {

  const container = document.getElementById("device_menu_status")
  if (container) {
    if (count > 0) {
      container.innerHTML = count;
    } else {
      container.innerHTML = "";
    }
  } else {
    console.log("did not find 'device_menu_status'")
  }
}