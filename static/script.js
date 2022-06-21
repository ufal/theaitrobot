
function show_hide(show_id, hide_id) {
    document.getElementById(show_id).style.display = "block";
    document.getElementById(hide_id).style.display = "none";
}

function typing() {
    document.getElementById('processing_block').style.display = "flex";
    document.body.style.cursor = 'wait'
    
    var blur_ids = [
        'main', 'main_2', 'theaitre', 'syn2script_controls', 'email_block'
    ];
    
    for (const blur_id of blur_ids) {
        elem = document.getElementById(blur_id);
        if (elem) {
            elem.style.filter = "blur(8px)";
        }
    }

}

function page_loaded() {
    // no typing
    document.getElementById('processing_block').style.display = "none"
    document.getElementById('main').style.filter = "blur(0px)"
    document.body.style.cursor = 'default'
    // set URL
    history.replaceState({}, 'THEaiTRobot', document.body.getAttribute("data-thisurl"))
}


function Counter(elem, delay) {
    var value = parseInt(elem.getAttribute("data-value"), 10);
    var interval;

    var title = document.getElementById("title-switcher").innerHTML;

    var titles = [
      title,
      title + ".",
      title + "..",
      title + "...",
    ];

    function updateDisplay(value) {
      elem.innerHTML = value;
    }

    function run() {
      value += 1;
      if (value == titles.length) value = 0;

      elem.setAttribute("data-value", value);
      updateDisplay(titles[value]);
    }

    function start() {
      interval = window.setInterval(run, delay);
    }

    // exports
    // This actually creates a function that our counter can call
    // you'll see it used below.
    //
    // The other functions above cannot be accessed from outside
    // this function.
    this.start = start;
}

var elem = document.getElementById("title-switcher");

counter = new Counter(elem, 800);
counter.start();

buttons = [];
buttons = buttons.concat(
    Array.from(document.getElementsByClassName("add_tlacitko")),
    Array.from(document.getElementsByClassName("purple_tlacitko")),
    Array.from(document.getElementsByClassName("generovat")));
for (const button of buttons) {
    button.addEventListener("click", typing);
}

function scroll_to_end() {
    window.scrollTo(0,document.body.scrollHeight);
}

const scroll_to_end_bodies = ["body_script", "body_syn", "body_syn2script"];
if (scroll_to_end_bodies.includes(document.body.id)) {
    const myTimeout = setTimeout(scroll_to_end, 100);
    const myTimeout2 = setTimeout(page_loaded, 200);
} else {
    const myTimeout = setTimeout(page_loaded, 100);
}

