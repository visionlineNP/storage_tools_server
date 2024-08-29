
// tab_names is list of names
// parent is div element to attach the tabs
// prefix is name for the bs-target

function create_tabs(names, parent, prefix, event=null)
{

    rtn = {}

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
        const tab_name = prefix + ":" + item_name;
        link.setAttribute("data-bs-toggle", "tab");
        link.setAttribute("data-bs-target", "#" + tab_name);
        link.type = "button";
        link.role = "tab";
        link.setAttribute("aria-controls", tab_name);

        if(event) {
            // execute this function once the tab is visible for the first time
            link.addEventListener("show.bs.tab", function(e) {
                // console.log(e, event, tab_name);
                socket.emit(event, {tab:tab_name})
            },{once: true})
        }
    }

    const tab_contents = document.createElement("div");
    tab_contents.className = "tab-content";
    parent.appendChild(tab_contents);
    first_name = true;
    for (const item_name of names) {
        let was_first = false;
        let tab_div = document.createElement("div");
        tab_contents.appendChild(tab_div);
        if (first_name) {
            tab_div.className = "tab-pane fade show active";
            first_name = false;
            was_first = true;
        } else {
            tab_div.className = "tab-pane fade hidden";
        }
        const tab_name = prefix + ":" + item_name;
        tab_div.id = tab_name;
        tab_div.role = "tabpanel";
        tab_div.setAttribute("aria-labelledby", tab_name);
        tab_div.tabIndex = "0";

        rtn[item_name] = tab_div;

        if(event && was_first) {
            // always make sure the first one is triggered. 
            // console.log(event, tab_name);
            socket.emit(event, {tab:tab_name})
        }
    }

    return rtn;
}

function add_placeholder(div)
{
    const p = document.createElement("p");
    p.className = "placeholder-glow";
    p.setAttribute("aria-hidden", "true");
    div.appendChild(p);
    const sizes = [7,4, 2, 8, 4,4,6,9];
    $.each(sizes, function(_, sz) {
        const span = document.createElement("span");
        p.appendChild(span);
        span.className = "placeholder col-" + sz;

        const space = document.createElement("span");
        p.append(space);
        space.textContent = " ";
    });

}