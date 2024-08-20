
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

  });

  socket.on("disconnect", function () {

    var statusDiv = document.getElementById('connection_status');
    if (!statusDiv.classList.contains('offline')) {
      statusDiv.classList.add('offline');
      statusDiv.textContent = 'Offline';
      //statusDiv.style.backgroundColor = 'red';
    }

  });

  // process data device 
  socket.on('device_data', function (data) {
    console.log('Received data_device:', data);
    updateDeviceData(data);
  });

  socket.on('device_status', function (data) {
    updateDeviceStatus(data);
  });

  socket.on('device_status_tqdm', function (msg) {
    updateProgress(msg, 'device-status-tqdm');
  });

  socket.on('node_status_tqdm', function (msg) {
    updateProgress(msg, 'task-node-status-tqdm');
  }
  );

  socket.on("server_status_tqdm", function(msg) {
    updateProgress(msg, "server-status-tqdm");
  })


  socket.on('node_data', function (data) {
    console.log('Received node_data:', data);
    updateNodeData(data);
  });

  socket.on('server_data', function (data) {
    //console.log('Received server_data:', data);
    updateServerData(data);
  });


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

  socket.on("remote_connection", function(msg) {
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

  document.getElementById('add-project-btn').addEventListener('click', function () {
    const projectName = document.getElementById('project-name-input').value;
    if (projectName) {
      socket.emit('add_project', { project: projectName });
      document.getElementById('project-name-input').value = '';
    }
    populateEditMenus();
  });


  document.getElementById('add-robot-btn').addEventListener('click', function () {
    const robotName = document.getElementById('robot-name-input').value;
    if (robotName) {
      socket.emit('add_robot', { robot: robotName });
      document.getElementById('robot-name-input').value = '';
    }
  });

  document.getElementById('add-site-btn').addEventListener('click', function () {
    const siteName = document.getElementById('site-name-input').value;
    if (siteName) {
      socket.emit('add_site', { site: siteName });
      document.getElementById('site-name-input').value = '';
    }
  });


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



// function updateNodeData(data) {
//   let container = $('#node-data-container');
//   container.empty(); // Clear previous data

//   $.each(data, function (source, source_item) {

//     let sourceHtml = '<h2>' + source + '</h2><ul>';

//     $.each(source_item.fs_info, function (_, info) {
//       sourceHtml += '<li>' + info[0] + ' : <b>' + info[1] + '%</b> free</li>';
//     });

//     sourceHtml += '</ul><div class="btn-group">' +
//       '<button type="button" class="btn btn-primary" id="select-new-' + source + '">Select All New</button>' +
//       '<button type="button" class="btn btn-secondary" id="clear-all-' + source + '">Clear Selections</button>' +
//       '<button type="button" class="btn btn-success" id="transfer-selected-' + source + '">Transfer Selected</button>' +
//       '<button type="button" class="btn btn-danger" id="cancel-' + source + '">Stop Transfer</button>' +
//       '<button type="button" class="btn btn-danger" id="remove-selected-' + source + '">Removed Completed</button>' +
//       '</div><div class="btn-group">' +
//       '<button type="button" class="btn btn-primary" id="rescan-' + source + '">Scan</button>' +
//       '</div>';

//     sourceHtml += '<table class="table table-striped">' +
//       '<thead><tr>' +
//       '<th></th>' +
//       '<th>Project</th>' +
//       '<th>Name</th>' +
//       '<th>Rel Path</th>' +
//       '<th>Basename</th>' +
//       '<th>DateTime</th>' +
//       '<th>File size</th>' +
//       '<th>State</th>' +
//       '</tr></thead><tbody>';

//     $.each(source_item.entries, function (_, entry) {
//       sourceHtml += '<tr>' +
//         '<td><input type="checkbox" id="' + entry.upload_id + '" data-source="' + source + '" data-on-device="' + entry.on_device + '" data-on-server="' + entry.on_server + '"></td>' +
//         '<td>' + entry.project + '</td>' +
//         '<td>' + entry.robot_name + '</td>' +
//         '<td style="overflow-x:scroll;">' + entry.relpath + '</td>' +
//         '<td>' + entry.basename + '</td>' +
//         '<td>' + entry.datetime + '</td>' +
//         '<td>' + entry.size + '</td>' +
//         '<td><div id="status_' + entry.upload_id + '" class="status-div">' + entry.status + '</div></td>' +
//         '</tr>';
//     });

//     sourceHtml += '</tbody></table>';
//     container.append(sourceHtml);

//     // attachEventHandlers();
//   });

//   // subscribe to each room.  
//   $.each(data, function (source, source_item) {
//     socket.emit('join', { 'room': source });
//   });

//   // Re-attach event handlers after dynamic content insertion
//   //attachEventHandlers();
// };


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
      socket.emit('add_site', { site: newSite });
      // Add new site to the global sites array and update all dropdowns
      window.sites.push(newSite);
      updateAllSiteSelects();
      // Set the new site as the selected value
      $(this).val(newSite);
    }
  } else {
    // Emit event to update the site for this entry
    socket.emit('update_entry_site', { source: source, upload_id: uploadId, site: selectedValue });
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
    msg = { "source": source, "files": selectedUpdateIds };
    socket.emit("device_remove", msg);
  } else {
    alert('No files selected');
  }
};


/// cancel transfers
function cancelTransfers(source) {
  socket.emit("control_msg", { "source": source, "action": "cancel" });
  // $.ajax({
  //   type: 'GET',
  //   url: '/cancel/' + source,
  //   success: function (data) {
  //     console.log('Transfers Canceled');
  //   },
  //   error: function (xhr, status, error) {
  //     console.error('Error in canceling:', error);
  //   }
  // });
};

/// --------

/// rescan source
function rescanSource(source) {
  socket.emit("device_scan", { "source": source });
  // $.ajax({
  //   type: 'GET',
  //   url: '/rescan/' + source,
  //   success: function (data) {
  //     console.log('Rescan Canceled');
  //   },
  //   error: function (xhr, status, error) {
  //     console.error('Error in rescanning:', error);
  //   }
  // });
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
  let projectList = document.getElementById('project-list');
  projectList.innerHTML = ''; // Clear existing list
  window.projects = []

  // Create the <ul> element with class "list-group"
  const ul = document.createElement('ul');
  ul.className = 'list-group';

  // Create and append <li> elements for each project
  projectData.forEach(item => {
    const li = document.createElement('li');
    li.className = 'list-group-item';
    li.textContent = item;
    ul.appendChild(li);
    window.projects.push(item);
  });

  // Append the <ul> to the project list container
  projectList.appendChild(ul);
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

  window.projects.forEach(project => {
    $.each(projectMenu, function (_, menudiv) {
      const source = menudiv.dataset.source;
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
      "project": newProject
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
  socket.emit('debug_clear_data');
}

function refreshTooltips() {
  const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]')
  const tooltipList = [...tooltipTriggerList].map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl))
}


function getCookie(name) {
  let cookies = document.cookie.split(';');
  for (let i = 0; i < cookies.length; i++) {
    let cookie = cookies[i].trim();
    // Check if this cookie matches the name we are looking for
    if (cookie.startsWith(name + '=')) {
      return cookie.substring(name.length + 1);
    }
  }
  return null;
}

// Function to delete a specific cookie by name
function deleteCookie(name) {
  document.cookie = name + '=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
}

function logout() {
  console.log("logout");
  deleteCookie("username");
  deleteCookie("api_key_token");
  deleteCookie("password");
  window.location.reload();
}



window.sites = [];
window.robots = [];
window.projects = [];
window.allProgressBars = {};