$( document ).ready(function() {
    $("#usertoview").change(pick_different_user)
})

function pick_different_user(){
    username = $("#usertoview").val()
    window.location.replace("/storage/"+username);
}
