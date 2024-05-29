$( document ).ready(function() {

    $("#previousdates").change(pick_compare_date)

    show_previous_folders()

})

function pick_compare_date(){
    let compare_date = $("#previousdates").val()
    if (compare_date=="None") {
        window.location.replace("/allstorage");

    }
    else {
        window.location.replace("/allstorage/"+compare_date);
    }
}