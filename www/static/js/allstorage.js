$( document ).ready(function() {

    $("#previousdates").change(pick_compare_date)
    

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