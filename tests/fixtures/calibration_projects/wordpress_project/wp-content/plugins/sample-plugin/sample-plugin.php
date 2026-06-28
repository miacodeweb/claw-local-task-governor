<?php
/**
 * Plugin Name: Sample Plugin
 * Description: Calibration fixture plugin
 * Version: 1.0.0
 */

function sample_plugin_enqueue_scripts() {
    wp_enqueue_style('sample-style', plugins_url('style.css', __FILE__));
}
add_action('wp_enqueue_scripts', 'sample_plugin_enqueue_scripts');

function sample_shortcode_handler($atts) {
    return 'Hello from Sample Plugin';
}
add_shortcode('sample', 'sample_shortcode_handler');
