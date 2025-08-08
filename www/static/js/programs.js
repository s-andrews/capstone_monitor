$( document ).ready(function() {
    $("#startrstudio").click(start_rstudio)
    $("#stoprstudio").click(stop_rstudio)
    $("#rstudiomemory").on(
        "input",
        function(x) {
            $("#selectedrstudiomemory").text($("#rstudiomemory").val())
        }
    )

    $("#startjupyterlab").click(start_jupyterlab)
    $("#stopjupyterlab").click(stop_jupyterlab)
    $("#jupyterlabmemory").on(
        "input",
        function(x) {
            $("#selectedjupyterlabmemory").text($("#jupyterlabmemory").val())
        }
    )

    $("#startfilebrowser").click(start_filebrowser)
    $("#stopfilebrowser").click(stop_filebrowser)

    $("#startollama").click(start_ollama)
    $("#stopollama").click(stop_ollama)

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


function stop_jupyterlab() {

    console.log("Stopping Jupyterlab")
    $("#stopjupyterlab").prop("disabled",true)

    $("#stopjupyterlab").html(
        `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Stopping...`
    );

}

function start_jupyterlab() {

    $("#startjupyterlab").prop("disabled",true)

    $("#startjupyterlab").html(
        `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Starting...`
    );

    let memory = $("#jupyterlabmemory").val()

    console.log("Launching jupyterlab")
    $.ajax(
        {
            url: "/launch_program/jupyterlab/"+memory,
            method: "GET",
            success: function() {
                location.reload()
            },
            error: function(message) {
            }
        }
    )
}

function stop_filebrowser() {

    console.log("Stopping Filebrowser")
    $("#stopfilebrowser").prop("disabled",true)

    $("#stopfilebrowser").html(
        `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Stopping...`
    );

}

function start_filebrowser() {

    $("#startfilebrowser").prop("disabled",true)

    $("#startfilebrowser").html(
        `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Starting...`
    );

    let share = $("#filebrowsershare").val()

    console.log("Launching filebrowser")
    $.ajax(
        {
            url: "/launch_program/filebrowser/"+share,
            method: "GET",
            success: function() {
                location.reload()
            },
            error: function(message) {
            }
        }
    )
}


function stop_ollama() {

    console.log("Stopping Ollama")
    $("#stopollama").prop("disabled",true)

    $("#stopollama").html(
        `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Stopping...`
    );

}

function start_ollama() {

    $("#startollama").prop("disabled",true)

    $("#startollama").html(
        `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Starting...`
    );

    console.log("Launching ollama")
    $.ajax(
        {
            url: "/launch_program/ollama",
            method: "GET",
            success: function() {
                location.reload()
            },
            error: function(message) {
            }
        }
    )
}

