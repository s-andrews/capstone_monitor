$( document ).ready(function() {
    $("#startrstudio").click(start_rstudio)
    $("#stoprstudio").click(stop_rstudio)
    $("#rstudiomemory").on(
        "input",
        function(x) {
            $("#selectedrstudiomemory").text($("#rstudiomemory").val())
        }
    )
})


function stop_rstudio() {

    console.log("Stopping RStudio")
    $("#stoprstudio").prop("disabled",true)

    $("#stoprstudio").html(
        `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Stopping...`
    );

}

function start_rstudio() {

    $("#startrstudio").prop("disabled",true)

    $("#startrstudio").html(
        `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Starting...`
    );

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
