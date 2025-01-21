// Animación de puntos suspensivos
function animateDots(loadingTextElement) {
    let dots = 0;
    setInterval(() => {
        dots = (dots + 1) % 4; // Ciclar entre 0 y 3 puntos
        loadingTextElement.text("Cargando datos" + ".".repeat(dots));
    }, 500);
}

// Mostrar loader
function showLoader() {
    const loader = $("#loader");
    const loadingText = $("#loading-text");
    loader.show();
    animateDots(loadingText);
}

// Ocultar loader
function hideLoader() {
    $("#loader").hide();
}

// Verificar y cargar datos
function loadData() {
    if (!localStorage.getItem("data_loaded")) {
        showLoader();
        $.ajax({
            url: loadComidasUrl, // Esta URL debe definirse en el template
            type: "GET",
            success: function (response) {
                if (response.success) {
                    localStorage.setItem("data_loaded", "true"); // Marca los datos como cargados
                    //location.reload(); // Recarga para usar los datos
                } else {
                    console.error("Error al cargar las comidas:", response.error);
                }
            },
            error: function (xhr) {
                if (xhr.status === 403) {
                    // Redirección basada en la respuesta del middleware
                    const redirectUrl = JSON.parse(xhr.responseText).redirect_url;
                    window.location.href = redirectUrl;
                } else {
                    console.error("Error al comunicarse con el servidor.");
                }
            },
            complete: function () {
                hideLoader(); // Ocultar loader después de la solicitud
            }
        });
    }
}

// Configuración de datos básicos
function setBasicData() {
    // Recuperar datos del storage al cargar la página
    const storedBasicData = JSON.parse(localStorage.getItem("basicData")) || {};
    if (storedBasicData.name) $("#name").val(storedBasicData.name);
    if (storedBasicData.birthdate) $("#birthdate").val(storedBasicData.birthdate);
    if (storedBasicData.gender) $("#gender").val(storedBasicData.gender);
    if (storedBasicData.physical_activity !== undefined) {
        $(`input[name="physical_activity"][value="${storedBasicData.physical_activity}"]`).prop("checked", true);
    }
    if (storedBasicData.weight) $("#weight").val(storedBasicData.weight);

    // Guardar datos en el localStorage al enviar el formulario
    $("#user-form").on("submit", function () {
        const name = $("#name").val();
        const birthdate = $("#birthdate").val();
        const gender = $("#gender").val();
        const physicalActivity = $("input[name='physical_activity']:checked").val();
        const weight = $("#weight").val();

        // Guardar datos en el localStorage
        const basicData = { name, birthdate, gender, physical_activity: physicalActivity, weight };
        localStorage.setItem("basicData", JSON.stringify(basicData));
    });

    // Cargar datos
    // descomentar si queremos que se carguen los datos solo si no se han cargado con anterioridad.
    //loadData();

    
    // Siempre recargar datos desde el backend
    // Comentar si queremos que no se carguen siempre
    showLoader();
    $.ajax({
        url: loadComidasUrl, // Esta URL debe definirse en el template
        type: "GET",
        success: function (response) {
            if (response.success) {
                //location.reload(); // Recarga para usar los datos
            } else {
                console.error("Error al cargar las comidas:", response.error);
            }
        },
        error: function (xhr) {
            if (xhr.status === 403) {
                // Redirección basada en la respuesta del middleware
                const redirectUrl = JSON.parse(xhr.responseText).redirect_url;
                window.location.href = redirectUrl;
            } else {
                console.error("Error al comunicarse con el servidor.");
            }
        },
        complete: function () {
            hideLoader(); // Ocultar loader después de la solicitud
        }
    });
}
