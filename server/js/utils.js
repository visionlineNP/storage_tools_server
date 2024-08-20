
// tab_names is list of names
// parent is div element to attach the tabs
// prefix is name for the bs-target

function create_tabs(names, parent, prefix)
{

    rtn = {}
    // names = Object.entries(tab_names);
    // names.sort((a, b) => a[0].localeCompare(b[0]));

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
        link.setAttribute("data-bs-toggle", "tab");
        link.setAttribute("data-bs-target", "#" + prefix + "-" + item_name);
        link.type = "button";
        link.role = "tab";
        link.setAttribute("aria-controls", prefix + "-" + item_name);
    }

    const tab_contents = document.createElement("div");
    tab_contents.className = "tab-content";
    parent.appendChild(tab_contents);
    first_name = true;
    for (const item_name of names) {

        let tab_div = document.createElement("div");
        tab_contents.appendChild(tab_div);
        if (first_name) {
            tab_div.className = "tab-pane fade show active";
            first_name = false;
        } else {
            tab_div.className = "tab-pane fade hidden";
        }
        tab_div.id = prefix + "-" + item_name;
        tab_div.role = "tabpanel";
        tab_div.setAttribute("aria-labelledby", prefix+ "-" + item_name);
        tab_div.tabIndex = "0";

        rtn[item_name] = tab_div;
    }

    return rtn;
}