function updateProgress(msg, container) {
  let source = msg.source;
  let position = msg.position;
  let progress = msg.progress;
  let total = msg.total;
  let rate = msg.rate;
  let remaining = msg.remaining;

  let allProgressBars = window.allProgressBars;
  let desc = "[" + source + "] " + msg.desc;
  let statusContainer = document.getElementById(container);

  if (statusContainer == null) {
    console.log("Did not find " + container);
    return;
  }

  if (!Reflect.has(allProgressBars, source)) {
    allProgressBars[source] = {};
  }

  // Update progress percentage
  if (progress > -1) {
    let progressPercentage = (progress / total) * 100;
    allProgressBars[source][position] = progressPercentage;
  } else {
    if (Reflect.has(allProgressBars[source], position)) {
      Reflect.deleteProperty(allProgressBars[source], position)
    }
  }

  // Update header
  let statusHeader = document.getElementById(container + "-header");
  if (statusHeader != null) {
    let line = "<b>Progress</b> ";
    const bySource = Object.entries(allProgressBars).sort((a, b) => a[0].localeCompare(b[0]));
    for (const [titleSource, titleBars] of bySource) {
      const bars = Object.entries(titleBars);
      if (bars.length > 0) {
        for (let index = 0; index < bars.length; index++) {
          const [pos, prog] = bars[index];
          if (pos == 0) line += ` ${titleSource}:${Math.round(prog)}%`;
        }
      }
    }
    statusHeader.innerHTML = line;
  } else {
    console.log("Did not find [" + container  + "-header]");
  }

  // Update or add sourceDiv
  let sourceDiv = document.getElementById('source_' + source);
  if (!sourceDiv) {
    sourceDiv = document.createElement('div');
    sourceDiv.id = 'source_' + source;
    statusContainer.appendChild(sourceDiv);
  }

  // Update or add positionDiv
  let positionDiv = document.getElementById('position_' + source + '_' + position);
  if (progress === -1) {
    if (positionDiv) {
      sourceDiv.removeChild(positionDiv);
    }
    return;
  }
  if (!positionDiv) {
    positionDiv = document.createElement('div');
    positionDiv.id = 'position_' + source + '_' + position;
    positionDiv.className = 'progress-container';

    let progressBarContainer = document.createElement('div');
    progressBarContainer.className = 'progress';

    let progressBar = document.createElement('div');
    progressBar.className = 'progress-bar overflow-visible text-dark ' + (position === 0 ? 'bg-info' : 'bg-warning');
    progressBar.id = 'progress_' + source + '_' + position;
    progressBar.setAttribute('role', 'progressbar');
    progressBar.setAttribute('aria-valuemin', '0');
    progressBar.setAttribute('aria-valuemax', total);
    progressBar.style.setProperty("text-align", "left");

    progressBarContainer.appendChild(progressBar);
    positionDiv.appendChild(progressBarContainer);
    sourceDiv.appendChild(positionDiv);
  }

  // Update progress bar
  let progressBar = document.getElementById('progress_' + source + '_' + position);
  let progressPercentage = (progress / total) * 100;
  progressBar.style.width = progressPercentage + '%';
  progressBar.setAttribute('aria-valuenow', progress);
  let innerHTML = desc ? `${desc}: ${Math.round(progressPercentage)}%` : `${Math.round(progressPercentage)}%`;
  if (rate != null) {
    innerHTML += ` : ${rate} : ${remaining}`;
  }
  progressBar.innerHTML = innerHTML;

  // Manage container height
  const initialHeight = statusContainer.clientHeight;
  if (statusContainer.scrollHeight > initialHeight) {
    statusContainer.style.height = `${statusContainer.scrollHeight}px`;
  }
}
