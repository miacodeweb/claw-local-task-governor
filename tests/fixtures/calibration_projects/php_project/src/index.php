<?php

function loadTemplate($name) {
    $path = $_GET['template'] ?? 'default';
    $content = file_get_contents("/templates/" . $name . ".html");
    return $content;
}

echo loadTemplate("home");
