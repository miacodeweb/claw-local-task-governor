<?php
/**
 * The base configuration for WordPress
 *
 * @package WordPress
 */

define('DB_NAME', 'database_name_here');
define('DB_USER', 'username_here');
define('DB_PASSWORD', 'password_here');
define('DB_HOST', 'localhost');

$table_prefix = 'wp_';

define('WP_DEBUG', true);

if (!defined('ABSPATH')) {
    define('ABSPATH', __DIR__ . '/');
}

require_once ABSPATH . 'wp-settings.php';
