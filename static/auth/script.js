
function myFunction(){
    console.log(1);
}

function clearSelect(sel){
    var i;
    for(i=sel.options.length-1; i>=0; i--){
        sel.remove(i);
    }
}

function changeMake(sel) {
  console.log(sel);
    var selected_make = sel.options[sel.selectedIndex].value;
    var select_model = document.getElementById('model');
    console.log(selected_make);
    // Remove all select options
    clearSelect(select_model);

    // Loop through each model of the selected make
    $.each(cars[selected_make], function(index, model) {
        // Create select option
        var option = document.createElement("option");
        option.text = model;
        option.value = model;
        // Add option to select
        select_model.options.add(option);
    });
}