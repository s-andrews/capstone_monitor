$( document ).ready(function() {

    $("#previous_folders").click(show_previous_folders)
    $("#next_folders").click(show_next_folders)
    $("#usertoview").change(pick_different_user)

    show_previous_folders()

})

function pick_different_user(){
    console.log("Changed")
    username = $("#usertoview").val()
    window.location.replace("/folders/"+username);
}


function show_next_folders(){
    let folder_rows = $("tr.foldersize")

    // Find the last visible row
    let last_visible = folder_rows.length-1
    for (let i=0;i<folder_rows.length;i++) {
        if (folder_rows.eq(i).is(":visible")) {
            last_visible = i
        }
    }
    if (last_visible > folder_rows.length-5) {
        last_visible=folder_rows.length-5
    }
    folder_rows.hide()
    for (let i=last_visible+1;i<last_visible+6;i++) {
        folder_rows.eq(i).show()
    }
}

function show_previous_folders () {
    let folder_rows = $("tr.foldersize")

    // Find the first visible row
    let first_visible = 0
    for (let i=0;i<folder_rows.length;i++) {
        if (folder_rows.eq(i).is(":visible")) {
            first_visible = i
            break
        }
    }
    if (first_visible < 5) {
        first_visible=5
    }

    let start_visible = first_visible-5
    let end_visible = first_visible
    if (end_visible > folder_rows.length) {
        end_visible = folder_rows.length
    }

    folder_rows.hide()
    for (let i=start_visible;i<end_visible;i++) {
        folder_rows.eq(i).show()
    }
}