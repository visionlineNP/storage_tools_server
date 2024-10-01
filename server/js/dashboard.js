
/// --------------------------------------

/// handle on load
let autoRefreshInterval = null;

$(document).ready(function () {
  refreshTooltips();

  // connect to socket io.  
  socket.on('connect', function () {
    console.log('Connected to server');

    let statusDiv = document.getElementById('connection_status');
    if (statusDiv.classList.contains('offline')) {
      statusDiv.classList.remove('offline');
    }
    statusDiv.textContent = 'Online';

    username = getCookie("username");
    token = window.session_token;

    // socket.emit('join', {'room': 'dashboard-' + username, "type": "dashboard"})
    socket.emit('join', { 'room': 'dashboard-' + token, "type": "dashboard", "session_token": token })

  });

  socket.on("disconnect", function () {

    var statusDiv = document.getElementById('connection_status');
    if (!statusDiv.classList.contains('offline')) {
      statusDiv.classList.add('offline');
      statusDiv.textContent = 'Offline';
      //statusDiv.style.backgroundColor = 'red';
    }

  });

  // set new data 
  socket.on("has_new_data", function (data) {
    const has_new_data = data.value;
    const button = document.getElementById("new_data_button")
    if (button) {
      if (has_new_data) {
        button.innerHTML = "New Data"
        button.className = "btn btn-success"
      } else {
        button.innerHTML = "Refresh"
        button.className = "btn btn-secondary"
      }
    }
  })

  // process data device 
  socket.on('device_data', function (data) {
    console.log('Received data_device:', data);
    updateDeviceData(data);
  });

  socket.on('device_ymd_data', function (data) {
    // console.log(data)
    accumulateDeviceYMD(data);
  })

  socket.on('device_status', function (data) {
    updateDeviceStatus(data);
  });

  socket.on('device_revise_stats', function (data) {
    $.each(data, function (source_name, stats) {
      updateDeviceStats(source_name, stats);
    })
  })

  socket.on('device_status_tqdm', function (msg) {
    updateProgress(msg, 'device-status-tqdm');
  });

  socket.on('node_status_tqdm', function (msg) {
    updateProgress(msg, 'task-node-status-tqdm');
  }
  );

  socket.on("remote_data", function (msg) {
    updateServerRemote(msg);
  })

  socket.on("remote_ymd_data", function (msg) {
    console.log(msg)
    updateServerRemoteYMD(msg)
  })

  socket.on("server_status_tqdm", function (msg) {
    updateProgress(msg, "server-status-tqdm");
  })

  socket.on("server_ymd_data", function (msg) {
    accumulateServerYMD(msg);
  })

  socket.on('server_data', function (data) {
    //console.log('Received server_data:', data);
    updateServerData(data);
  });

  socket.on("server_regen_msg", function (data) {
    console.log(data)
    updateServerRegen(data)
  })

  socket.on('server_error', function (data) {
    alert(data.msg);
  })

  socket.on("server_invalid_key", function (data) {
    serverInvalidKey(data);
  })

  socket.on('node_data', function (data) {
    console.log('Received node_data:', data);
    updateNodeData(data);
  });

  socket.on('node_ymd_data', function (msg) {
    processNodeYMD(msg);
  })

  socket.on('report_host_data', function (data) {
    console.log("Received report_host_data:", data);
    updateReportHostData(data);
  })

  socket.on('report_node_data', function (data) {
    console.log("Received report_node_data:", data);
    updateReportNodeData(data);
  })

  socket.on("dashboard_file_server", function (data) {
    on_dashboard_file_server(data);
  })

  socket.on("dashboard_update", on_dashboard_update)

  // process which files are on server and which are on device.  
  socket.on('dashboard_file', function (msg) {
    //console.log(msg);
    // let div_id = msg.div_id;
    // let div = document.getElementById(div_id);
    // if (div) {
    //   div.innerHTML = msg.status;
    // }

    console.log(msg);

    if (msg.on_server) {
      let check_id = msg.upload_id;
      let check = document.getElementById(check_id);
      if (check) {
        check.setAttribute("data-on-server", true);
      }
      node_id = "node_select_" + msg.upload_id;
      check = document.getElementById(node_id);
      if (check) {
        check.setAttribute("data-on-local", true);
      }

      let on_server_status = document.getElementById("on_server_" + msg.upload_id);
      if (on_server_status) {
        on_server_status.classList.remove("grayed-out");
        on_server_status.title = "On Server";
      }

      let on_remote_status = document.getElementById("node_on_local_" + msg.upload_id);
      if (on_remote_status) {
        on_remote_status.classList.remove("grayed-out");
        on_remote_status.title = "On Server";
      }
    } else {
      let on_server_status = document.getElementById("on_server_" + msg.upload_id);
      if (on_server_status) {
        on_server_status.classList.add("grayed-out");
        on_server_status.title = "Not On Server";
      }

      let on_remote_status = document.getElementById("node_on_local_" + msg.upload_id);
      if (on_remote_status) {
        on_remote_status.classList.add("grayed-out");
        on_remote_status.title = "Not On Server";
      }

    }

    if (msg.on_device) {
      let on_device_status = document.getElementById("on_device_" + msg.upload_id);
      if (on_device_status) {
        on_device_status.classList.remove("grayed-out");
      }
    } else {
      let on_device_status = document.getElementById("on_device_" + msg.upload_id);
      if (on_device_status) {
        on_device_status.classList.add("grayed-out");
      }
    }

    refreshTooltips();
  });


  socket.on("report_node_task_status", function (msg) {
    console.log(msg);
    let textarea = document.getElementById("report-host-console");
    let line = "pid: " + msg.parent_id + ", tid: " + msg.task_id + ", success: " + msg.success + ", status: " + msg.status + "\n";
    textarea.value += line;
  });

  socket.on("report_node_status", function (msg) {
    console.log(msg);
    let textarea = document.getElementById("report-host-console");
    let line = "task: " + msg.task_name + "tid: " + msg.task_id + ", action: " + msg.action + ", status: " + msg.status + "\n";
    textarea.value += line;

  });

  socket.on("remote_connection", function (msg) {
    on_remote_connection(msg);
  })


  // Config ----
  socket.on('project_names', function (msg) {
    updateProjectList(msg.data);
  });

  socket.on('robot_names', function (msg) {
    updateRobotList(msg.data);
  });

  socket.on('site_names', function (msg) {
    updateSiteList(msg.data);
  });

  socket.on('key_values', function (msg) {
    updateKeyValues(msg);
  });

  socket.on('generated_key', function (msg) {
    navigator.clipboard.writeText(msg.key);
  })


  // search
  socket.on("search_results", function (msg) {
    updateSearchResults(msg);
  })

  socket.on("search_filters", function (msg) {
    updateSearchFilters(msg);
  })

  // document.getElementById('add-project-btn').addEventListener('click', function () {
  //   const projectName = document.getElementById('project-name-input').value;
  //   if (projectName) {
  //     socket.emit('add_project', { project: projectName, "session_token": window.session_token });
  //     document.getElementById('project-name-input').value = '';
  //   }
  //   populateEditMenus();
  // });


  document.getElementById('add-robot-btn').addEventListener('click', function () {
    const robotName = document.getElementById('robot-name-input').value;
    if (robotName) {
      socket.emit('add_robot', { robot: robotName, "session_token": window.session_token });
      document.getElementById('robot-name-input').value = '';
    }
  });

  document.getElementById('add-site-btn').addEventListener('click', function () {
    const siteName = document.getElementById('site-name-input').value;
    if (siteName) {
      socket.emit('add_site', { site: siteName, "session_token": window.session_token });
      document.getElementById('site-name-input').value = '';
    }
  });

  document.getElementById('make-key-btn').addEventListener('click', function () {
    const input = document.getElementById('keys-name-input')
    const name = input.value;
    const source = input.dataset.source;

    if (name) {
      socket.emit('generate_key', { "name": name, "source": source, "session_token": window.session_token })
      input.value = "";
    }
  })

  document.getElementById("insert-key-btn").addEventListener('click', function () {
    const name = document.getElementById('insert-keys-name-input').value;
    const key = document.getElementById('insert-keys-value-input').value;

    if (name && key) {
      socket.emit("insert_key", { "name": name, "key": key, "session_token": window.session_token })

      document.getElementById('insert-keys-name-input').value = "";
      document.getElementById('insert-keys-value-input').value = "";
    }
  });

  document.getElementById("set-key-btn").addEventListener("click", function () {
    const key = document.getElementById("keys-set-api-key-input").value;

    if (key) {
      socket.emit("set_api_key_token", { "key": key, "session_token": window.session_token });
      document.getElementById("keys-set-api-key-input").value = "";
    }
  })

});


function updateDeviceStatus(data) {
  let container = $('#device-status-container');

  let source = data.source;

  let sourceDiv = document.getElementById('device_status_' + source);
  if (!sourceDiv) {
    sourceDiv = document.createElement('div');
    sourceDiv.id = 'device_status_' + source;
    container.append(sourceDiv);
  }

  sourceDiv.innerHTML = "";
  if (data.msg != null) {
    sourceDiv.innerHTML = "<b>" + source + "</b>: " + data.msg
  }

};



// Update all site select elements with the latest sites
function updateAllSiteSelects() {
  try {
    $('.site-select').each(function () {
      let source = $(this).attr("data-source");
      let upload_id = $(this).attr("data-upload-id");
      let currentSite = window.device_data[source][upload_id].site;

      let siteOptions = '<option value="" disabled>Select site</option>';
      $.each(window.sites, function (_, site) {
        siteOptions += '<option value="' + site + '"' + (site === currentSite ? ' selected' : '') + '>' + site + '</option>';
      });
      siteOptions += '<option value="add-new-site">Add New Site</option>';
      $(this).html(siteOptions);
    });
  } catch (error) {

  }
}

// Update all site select elements with the latest sites
function updateAllRobotSelects() {
  $('.robot-select').each(function () {
    let source = $(this).attr("data-source");
    let upload_id = $(this).attr("data-upload-id");
    let currentRobot = window.device_data[source][upload_id].robot_name;

    let robotOptions = '<option value="" disabled>Select robot</option>';
    $.each(window.robots, function (_, robot) {
      //console.log(robot, currentRobot, robot == currentRobot);
      robotOptions += '<option value="' + robot + '"' + (robot == currentRobot ? ' selected' : '') + '>' + robot + '</option>';
    });
    robotOptions += '<option value="add-new-robot">Add New Robot</option>';
    $(this).html(robotOptions);
  });
}




function updateServerDataOld(data) {
  let container = $("#server-fs-info-container");
  container.empty();
  sourceHtml = "<ul>";

  $.each(data.fs_info, function (_, info) {
    sourceHtml += '<li>' + info[0] + ' : <b>' + info[1] + '%</b> free</li>';
  });

  sourceHtml += "</ul>";
  container.append(sourceHtml);

  container = $('#server-data-container');
  container.empty(); // Clear previous data

  entries = data.entries;

  $.each(entries, function (project_name, projects) {
    let projectHtml = '<h2>' + project_name + '</h2>';

    $.each(projects, function (robot_name, robots) {
      projectHtml += '<h3>' + robot_name + '</h3>'
        + '<table class="table table-striped"><thead><tr>' +
        '<th>Select</th>' +
        '<th>Site</th>' +
        '<th>Date</th>' +
        '<th>Run</th>' +
        '<th>Relpath</th>' +
        '<th>Basename</th>' +
        '<th>Size</th>' +
        '<th>Status</th>' +
        '</tr></thead><tbody>';

      $.each(robots, function (_, run_details) {
        $.each(run_details, function (_, detail) {
          // console.log(detail);
          projectHtml += '<tr>' +
            '<td><input type="checkbox"></td>' +
            '<td>' + detail.site + '</td>' +
            '<td>' + detail.datetime + '</td>' +
            '<td>' + detail.run_name + '</td>' +
            '<td>' + detail.relpath + '</td>' +
            '<td>' + detail.basename + '</td>' +
            '<td>' + detail.size + '</td>' +
            '<td><div id="status_' + detail.upload_id + '" class="status-div">' + detail.status + '</div></td>' +
            '</tr>';
        });
      });

      projectHtml += '</tbody></table>';
    });

    container.append(projectHtml);
  });
}


function updateReportHostData(data) {
  container = $('#report-host-container');
  container.empty(); // Clear previous data

  reportHTML = "<ul>"
  $.each(data.hosts, function (_, hostname) {
    let buttons = "";
    buttons += "<button onclick='debug_countto(\"" + hostname + "\")' >Count</button>";
    buttons += "<button onclick='debug_count_to_next_task(\"" + hostname + "\")' >Count Next Task</button>";
    buttons += "<button onclick='task_reindex_all(\"" + hostname + "\")' >Reindex</button>";

    reportHTML += "<li>" + hostname + buttons + "</li>";
  });
  reportHTML += "</ul>"

  container.append(reportHTML);
}

function debug_countto(source) {
  socket.emit("debug_count_to", { "count_to": 10, "source": source })
}

function debug_count_to_next_task(source) {
  console.log("tick");
  socket.emit("debug_count_to_next_task", { "count_to": 10, "source": source })
}


function task_reindex_all(source) {
  socket.emit("task_reindex_all", { "source": source });
}

function updateReportNodeData(data) {
  container = $('#report-node-container');
  container.empty(); // Clear previous data

  reportHTML = "<ul>"
  $.each(data.nodes, function (hostname, entry) {
    reportHTML += "<li>";
    reportHTML += hostname;
    reportHTML += "<ul><li>Threads: " + entry.threads + "</li></ul>";
    reportHTML += "</li>";
  });
  reportHTML += "</ul>"

  container.append(reportHTML);
}




function processAddNewSite() {
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

}





/// ---- 
/// transfer of files 
function transferFiles(selectedUpdateIds, source) {
  if (selectedUpdateIds.length > 0) {
    $.ajax({
      type: 'POST',
      url: '/transfer-selected',
      data: JSON.stringify({ "source": source, "files": selectedUpdateIds }),
      contentType: 'application/json',
      success: function (data) {
        console.log('Files transferred successfully');
      },
      error: function (xhr, status, error) {
        console.error('Error transferring files:', error);
      }
    });
  } else {
    alert('No files selected');
  }
};

/// ----

/// remove files 

function removeFiles(selectedUpdateIds, source) {

  if (selectedUpdateIds.length > 0) {
    msg = { "source": source, "files": selectedUpdateIds, "session_token": window.session_token };
    console.log(msg);
    socket.emit("device_remove", msg);
  } else {
    alert('No files selected');
  }
};


/// cancel transfers
function cancelTransfers(source) {
  socket.emit("control_msg", { "source": source, "action": "cancel", "session_token": window.session_token });
};

/// --------

/// rescan source
function rescanSource(source) {
  socket.emit("device_scan", { "source": source, "session_token": window.session_token });
};


// update the date 
function postDateTimeChange(source, upload_id) {
  let datetimeInput = document.getElementById('date_' + upload_id);
  let newDateTime = datetimeInput.value;

  fetch('/update-datetime', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ datetime: newDateTime, source: source, upload_id: upload_id })
  })
    .then(response => response.json())
    .then(data => {
      console.log('DateTime updated successfully:', data);
      // Optionally update the UI to show that the update was successful
    })
    .catch((error) => {
      console.error('Error updating DateTime:', error);
      // Optionally handle UI changes on failure
    });
}

function updateProjectList(projectData) {

  window.projects = []

  {
    const tbody = document.querySelector('#projectTable tbody');
    tbody.innerHTML = '';  // Clear the table before updating

    // Create and append table rows for each project
    projectData.forEach(project => {
      const row = document.createElement('tr');

      // Project Name Cell
      const projectCell = document.createElement('td');
      projectCell.textContent = project.project;
      projectCell.classList.add("project")
      row.appendChild(projectCell);

      window.projects.push(project.project);

      // Volume Cell
      const volumeCell = document.createElement('td');
      const volumeSpan = document.createElement("span")
      volumeSpan.classList.add("volume")
      volumeSpan.textContent = project.volume;
      const volumeEdit = document.createElement("input")
      volumeEdit.type = "text";
      volumeEdit.classList.add("editVolume");
      volumeEdit.value = project.volume;
      volumeEdit.style.display = 'none';
      volumeCell.appendChild(volumeSpan);
      volumeCell.appendChild(volumeEdit);
      row.appendChild(volumeCell);

      // Description Cell (with edit capabilities)
      const descriptionCell = document.createElement('td');
      const descriptionSpan = document.createElement('span');
      descriptionSpan.classList.add('description');
      descriptionSpan.textContent = project.description;
      const descriptionInput = document.createElement('input');
      descriptionInput.type = 'text';
      descriptionInput.classList.add('editDescription');
      descriptionInput.value = project.description;
      descriptionInput.style.display = 'none';

      descriptionCell.appendChild(descriptionSpan);
      descriptionCell.appendChild(descriptionInput);
      row.appendChild(descriptionCell);

      // Actions Cell (Edit/Save/Cancel buttons)
      const actionsCell = document.createElement('td');
      const editButton = document.createElement('button');
      editButton.textContent = 'Edit';
      editButton.onclick = () => editProject(editButton);

      const saveButton = document.createElement('button');
      saveButton.textContent = 'Save';
      saveButton.style.display = 'none';
      saveButton.onclick = () => saveEdit(project.project, saveButton);

      const cancelButton = document.createElement('button');
      cancelButton.textContent = 'Cancel';
      cancelButton.style.display = 'none';
      cancelButton.onclick = () => cancelEdit(cancelButton);

      const deleteButton = document.createElement("button");
      deleteButton.textContent = "Delete";
      deleteButton.style.display = 'none';
      deleteButton.class = "btn btn-danger"
      deleteButton.onclick = () => deleteEdit(deleteButton);

      actionsCell.appendChild(editButton);
      actionsCell.appendChild(saveButton);
      actionsCell.appendChild(cancelButton);
      actionsCell.appendChild(deleteButton);

      row.appendChild(actionsCell);

      // Append the row to the table body
      tbody.appendChild(row);
    });
  }
  // update the user settings for project mount. 

  {
    const tbody = document.querySelector('#localMountTable tbody');
    tbody.innerHTML = '';  // Clear the table before updating

    // Create and append table rows for each project
    projectData.forEach(project => {
      const row = document.createElement('tr');

      // Project Name Cell
      const projectCell = document.createElement('td');
      projectCell.textContent = project.project;
      projectCell.classList.add("project")
      row.appendChild(projectCell);

      const cookieName = "mount_" + project.project;
      const mountPoint = getCookie(cookieName);

      // Volume Cell
      const mountCell = document.createElement('td');
      const mountSpan = document.createElement("span")
      mountSpan.classList.add("mount")
      if( mountPoint ) {
        mountSpan.textContent = mountPoint;
      }
      const mountEdit = document.createElement("input")
      mountEdit.type = "text";
      mountEdit.classList.add("editMount");
      mountEdit.value = mountPoint;
      mountEdit.style.display = 'none';
      mountCell.appendChild(mountSpan);
      mountCell.appendChild(mountEdit);
      row.appendChild(mountCell);

      // Actions Cell (Edit/Save/Cancel buttons)
      const actionsCell = document.createElement('td');
      const editButton = document.createElement('button');
      editButton.textContent = 'Edit';
      editButton.onclick = () => editProjectMount(editButton);

      const saveButton = document.createElement('button');
      saveButton.textContent = 'Save';
      saveButton.style.display = 'none';
      saveButton.onclick = () => saveEditMount(project.project, saveButton);

      const cancelButton = document.createElement('button');
      cancelButton.textContent = 'Cancel';
      cancelButton.style.display = 'none';
      cancelButton.onclick = () => cancelEditMount(cancelButton);


      actionsCell.appendChild(editButton);
      actionsCell.appendChild(saveButton);
      actionsCell.appendChild(cancelButton);

      row.appendChild(actionsCell);


      // Append the row to the table body
      tbody.appendChild(row);
    })
  }
}


function updateRobotList(robotData) {
  let robotList = document.getElementById('robot-list');
  robotList.innerHTML = ''; // Clear existing list
  window.robots = []; // clear the robot lists 

  // Create the <ul> element with class "list-group"
  const ul = document.createElement('ul');
  ul.className = 'list-group';

  // Create and append <li> elements for each project
  robotData.forEach(item => {
    const li = document.createElement('li');
    li.className = 'list-group-item';
    li.textContent = item;
    ul.appendChild(li);
    window.robots.push(item);
  });

  // Append the <ul> to the project list container
  robotList.appendChild(ul);

  updateAllRobotSelects();
  populateEditMenus();
}

function updateSiteList(siteData) {
  let siteList = document.getElementById('site-list');
  siteList.innerHTML = ''; // Clear existing list
  window.sites = [];

  // Create the <ul> element with class "list-group"
  const ul = document.createElement('ul');
  ul.className = 'list-group';

  siteData.forEach(item => {
    const li = document.createElement('li');
    li.className = 'list-group-item';
    li.textContent = item;
    ul.appendChild(li);
    window.sites.push(item);
  });

  siteList.appendChild(ul);

  updateAllSiteSelects();
  populateEditMenus();
}


function updateKeyValues(keyValues) {
  const source = keyValues.source;

  // show the current api key 
  const current = document.getElementById("current-api-key");
  current.innerHTML = keyValues.token;

  // attach the souce to the button so we can fetch it again. 
  const input = document.getElementById('keys-name-input')
  input.dataset.source = source;


  let keyList = document.getElementById('keys-list');
  keyList.innerHTML = '';


  const table = document.createElement("table");
  table.classList.add("table-fit")
  keyList.appendChild(table)

  const thead = document.createElement("thead");
  table.appendChild(thead);

  const hr = document.createElement("tr");
  thead.appendChild(hr);

  const header = ["Name", "API Key", ""];
  header.forEach(name => {
    const td = document.createElement("td");
    hr.appendChild(td);
    td.textContent = name;
    td.className = "key-table-header";
  });

  const tbody = document.createElement("tbody")
  table.appendChild(tbody);

  let entries = Object.entries(keyValues.data);
  entries = entries.sort((a, b) => a[1].localeCompare(b[1]));

  for (const [key, name] of entries) {
    const tr = document.createElement("tr")
    tbody.appendChild(tr);

    let td = document.createElement("td")
    td.textContent = name
    tr.appendChild(td);

    td = document.createElement("td")
    tr.appendChild(td)

    const key_span = document.createElement("input");
    key_span.type = "text"
    key_span.value = key
    key_span.readOnly = true;
    td.appendChild(key_span)


    td = document.createElement("td")
    tr.appendChild(td)
    const trash = document.createElement("i");
    trash.className = "bi bi-trash3";
    trash.title = "Delete Key";
    trash.dataset.key = key;
    trash.dataset.source = source;
    trash.dataset.name = name;
    trash.onclick = deleteKey;
    td.appendChild(trash);


    td = document.createElement("td")
    tr.appendChild(td)
    const copy = document.createElement("i");
    copy.className = "bi bi-copy";
    copy.title = "Copy to clipboard";
    copy.dataset.key = key;

    copy.addEventListener('click', function () {
      const key = $(this)[0].dataset.key;
      navigator.clipboard.writeText(key);
    })

    td.appendChild(copy)
  }


}


function deleteKey() {
  const key = $(this)[0].dataset.key;
  const source = $(this)[0].dataset.source;
  const name = $(this)[0].dataset.name;

  const msg = "Do you want to delete key for : " + name;
  console.log("Want to delete key " + key + " from " + source);

  const do_it = confirm(msg);
  if (do_it) {
    // console.log("I'm doing it");
    socket.emit("delete_key", { "key": key, "source": source, "name": name, "session_token": window.session_token })
  }
}


function downloadKeys() {
  console.log("download")

  const link = document.createElement("a")
  link.href = `/downloadKeys`
  link.download = "keys.yaml";
  link.style.display = 'none';

  document.body.appendChild(link);
  link.click()
  document.body.removeChild(link);

}

function uploadKeys() {

  const form = document.getElementById('uploadKeysForm');
  const formData = new FormData(form);

  fetch('/uploadKeys', {
    method: 'POST',
    body: formData
  })
    .then(response => response.json())
    .then(data => {
      // Display the message from the server
      console.log(data.message)
      //document.getElementById('message').innerText = data.message;
    })
    .catch(error => {
      console.error('Error:', error);
      //document.getElementById('message').innerText = 'An error occurred while uploading the file.';
    });

}

function populateEditMenus() {
  const siteMenu = $('.site-menu');
  const robotMenu = $('.robot-menu');
  const projectMenu = $('.project-menu');

  siteMenu.empty();
  robotMenu.empty();
  projectMenu.empty();

  // console.log(siteMenu);

  $.each(siteMenu, function (_, menuDiv) {
    const source = menuDiv.dataset.source;
    const date = menuDiv.dataset.date;
    window.sites.forEach(site => {
      $(menuDiv).append('<span class="dropdown-item update-site" data-source="' + source + '" data-date="' + date + '" data-site="' + site + '">' + site + '</span>');
    });

  });

  $.each(robotMenu, function (_, menuDiv) {
    const source = menuDiv.dataset.source;
    const date = menuDiv.dataset.date;
    window.robots.forEach(robot => {
      $(menuDiv).append('<span class="dropdown-item update-robot" data-source="' + source + '" data-date="' + date + '"  data-robot="' + robot + '">' + robot + '</span>');
    });


  });

  // Find each project menu and update them separately
  $('.project-menu').each(function () {
    const projectMenu = $(this);  // Select the current project menu div
    const source = projectMenu.data('source');  // Get the source associated with this menu

    // Clear the current menu
    projectMenu.empty();

    // Add projects to this specific menu
    window.projects.forEach(project => {
      projectMenu.append('<span class="dropdown-item update-project" data-source="' + source + '" data-project="' + project + '">' + project + '</span>');
    });
  });



  // Add event listeners for the site and robot menu items
  $('.update-site').on('click', function () {
    const newSite = $(this).data('site');
    const source = $(this).data('source');
    const date = $(this).data('date');

    $('input[type="checkbox"][data-group="table"][data-source="' + source + '"][data-date="' + date + '"]:checked').each(function () {
      const uploadId = $(this).attr('id');
      $('select.site-select[data-upload-id="' + uploadId + '"]').val(newSite).change();
    });
  });

  $('.update-robot').on('click', function () {
    const newRobot = $(this).data('robot');
    const source = $(this).data('source');
    const date = $(this).data('date');

    $('input[type="checkbox"][data-group="table"][data-source="' + source + '"][data-date="' + date + '"]:checked').each(function () {
      const uploadId = $(this).attr('id');
      $('select.robot-select[data-upload-id="' + uploadId + '"]').val(newRobot).change();
    });
  });


  $('.update-project').on('click', function () {
    const newProject = $(this).data('project');
    const source = $(this).data('source');
    socket.emit("set_project", {
      "source": source,
      "project": newProject, "session_token": window.session_token
    });

    updateDeviceData({})
    // // Close the dropdown
    // var dropdownMenu = $(this).closest('.dropdown-menu');
    // var dropdownToggle = dropdownMenu.prev('.dropdown-toggle');
    // dropdownToggle.dropdown('toggle');

  });

}


function debugClearData() {
  console.log("clearing the database!");
  data = { "session_token": window.session_token }
  socket.emit('debug_clear_data', data);
}

function refreshTooltips() {
  const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]')
  const tooltipList = [...tooltipTriggerList].map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl))
}



function logout() {
  console.log("logout");
  deleteCookie("username");
  deleteCookie("api_key_token");
  deleteCookie("password");
  deleteCookie("session_token")
  window.location.reload();
}



// Add a new project
function addProject() {
  const project = document.getElementById('newProject').value;
  const volume = document.getElementById('newVolume').value;
  const description = document.getElementById('newDescription').value;

  // Emit the "add_project" event
  socket.emit('add_project', { project, volume, description, "session_token": window.session_token });

  // Clear the input fields
  document.getElementById('newProject').value = '';
  document.getElementById('newVolume').value = '';
  document.getElementById('newDescription').value = '';
}

// Edit an existing project
function editProject( btn) {
  const row = btn.closest('tr');
  row.querySelector('.description').style.display = 'none';  // Hide description
  row.querySelector('.editDescription').style.display = '';  // Show edit field
  btn.style.display = 'none';  // Hide "Edit" button

  row.querySelector('.volume').style.display = 'none';
  row.querySelector('.editVolume').style.display = '';

  row.querySelectorAll('button')[1].style.display = '';  // Show "Save" button
  row.querySelectorAll('button')[2].style.display = '';  // Show "Cancel" button
  row.querySelectorAll('button')[3].style.display = '';  // Hide "Delete" button
}

// Save the edited project
function saveEdit(project, btn) {
  const row = btn.closest('tr');
  const newDescription = row.querySelector('.editDescription').value;
  const newVolume = row.querySelector('.editVolume').value

  // Emit the "edit_project" event
  socket.emit('edit_project', { project: project, volume: newVolume, description: newDescription, "session_token": window.session_token });

  // Revert to display mode
  row.querySelector('.description').textContent = newDescription;
  row.querySelector('.description').style.display = '';  // Show description
  row.querySelector('.editDescription').style.display = 'none';  // Hide edit field
  row.querySelector('.volume').textContent = newVolume;
  row.querySelector('.volume').style.display = '';
  row.querySelector('.editVolume').style.display = 'none';

  row.querySelectorAll('button')[0].style.display = '';  // Show "Edit" button
  row.querySelectorAll('button')[1].style.display = 'none';  // Hide "Save" button
  row.querySelectorAll('button')[2].style.display = 'none';  // Hide "Cancel" button
  row.querySelectorAll('button')[3].style.display = 'none';  // Hide "Delete" button
}

// Cancel editing a project
function cancelEdit(btn) {
  const row = btn.closest('tr');
  row.querySelector('.description').style.display = '';  // Show description
  row.querySelector('.editDescription').style.display = 'none';  // Hide edit field
  row.querySelector('.volume').style.display = '';
  row.querySelector('.editVolume').style.display = 'none';

  row.querySelectorAll('button')[0].style.display = '';  // Show "Edit" button
  row.querySelectorAll('button')[1].style.display = 'none';  // Hide "Save" button
  row.querySelectorAll('button')[2].style.display = 'none';  // Hide "Cancel" button
  row.querySelectorAll('button')[3].style.display = 'none';  // Hide "Delete" button
}


function deleteEdit(btn) {
  const row = btn.closest('tr');
  const project = row.querySelector(".project").textContent
  const answer = confirm("Really delete [" + project + "]? This only deletes the project entry, not the files associated with the project.");
  console.log(answer);
  if (answer) {
    socket.emit('delete_project', { project: project, "session_token": window.session_token });
  }

  row.querySelectorAll('button')[0].style.display = '';  // Show "Edit" button
  row.querySelectorAll('button')[1].style.display = 'none';  // Hide "Save" button
  row.querySelectorAll('button')[2].style.display = 'none';  // Hide "Cancel" button
  row.querySelectorAll('button')[3].style.display = 'none';  // Hide "Delete" button

}



function editProjectMount( btn) {
  const row = btn.closest('tr');
  btn.style.display = 'none';  // Hide "Edit" button

  row.querySelector('.mount').style.display = 'none';
  row.querySelector('.editMount').style.display = '';

  row.querySelectorAll('button')[1].style.display = '';  // Show "Save" button
  row.querySelectorAll('button')[2].style.display = '';  // Show "Cancel" button
}


// Save the edited project
function saveEditMount(project, btn) {
  const row = btn.closest('tr');
  const newMount = row.querySelector('.editMount').value

  setCookie("mount_" + project, newMount)

  // Revert to display mode
  row.querySelector('.mount').textContent = newMount;
  row.querySelector('.mount').style.display = '';
  row.querySelector('.editMount').style.display = 'none';

  row.querySelectorAll('button')[0].style.display = '';  // Show "Edit" button
  row.querySelectorAll('button')[1].style.display = 'none';  // Hide "Save" button
  row.querySelectorAll('button')[2].style.display = 'none';  // Hide "Cancel" button
}

function cancelEditMount(btn) {
  const row = btn.closest('tr');
  row.querySelector('.mount').style.display = '';
  row.querySelector('.editMount').style.display = 'none';

  row.querySelectorAll('button')[0].style.display = '';  // Show "Edit" button
  row.querySelectorAll('button')[1].style.display = 'none';  // Hide "Save" button
  row.querySelectorAll('button')[2].style.display = 'none';  // Hide "Cancel" button
}



function request_new_data() {
  msg = {
    "session_token": window.session_token
  }

  socket.emit("request_new_data", msg)
}

window.sites = [];
window.robots = [];
window.projects = [];
window.allProgressBars = {};