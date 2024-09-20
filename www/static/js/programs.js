$( document ).ready(function() {
    $("#startrstudio").click(start_rstudio)
    $("#rstudiomemory").on(
        "input",
        function(x) {
            $("#selectedrstudiomemory").text($("#rstudiomemory").val())
        }
    )
})


function start_rstudio() {
    let memory = $("#rstudiomemory").val()

    console.log("Launching rstudio")
    $.ajax(
        {
            url: "/launch_program/rstudio/"+memory,
            method: "GET",
            success: function() {
                location.reload()
            },
            error: function(message) {
            }
        }
    )


}
