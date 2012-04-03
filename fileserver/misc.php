<?php

include_once 'version.php';

/**
 * A userid length (SHA-1 hash)
 * @var int
 */
define('USERID_LENGTH', 40);

/**
 * A userid length + resource
 * @var int
 */
define('USERID_LENGTH_RESOURCE', 48);


define('CHARSBOX_AZN_CASEINS', 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz1234567890');
define('CHARSBOX_AZN_LOWERCASE', 'abcdefghijklmnopqrstuvwxyz1234567890');
define('CHARSBOX_AZN_UPPERCASE', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890');

/**
 * Produces a random string.
 * @param int $length
 * @param string $chars
 */
function rand_str($length = 32, $chars = CHARSBOX_AZN_CASEINS)
{
    // Length of character list
    $chars_length = (strlen($chars) - 1);

    // Start our string
    $string = $chars{rand(0, $chars_length)};

    // Generate random string
    for ($i = 1; $i < $length; $i = strlen($string))
    {
        // Grab a random character from our list
        $r = $chars{rand(0, $chars_length)};

        // Make sure the same two characters don't appear next to each other
        if ($r != $string{$i - 1}) $string .=  $r;
    }

    // Return the string
    return $string;
}

/**
 * @todo
 * @param array $ar
 * @param mixed $key
 * @param mixed $def
 * @return mixed
 */
function array_get($ar, $key, $def = false)
{
    return (isset($ar[$key])) ? $ar[$key] : $def;
}

/**
 * Sends a 400 Bad Request to the client.
 * Warning: this function DOES NOT RETURN!
 * @param $string $str optional response body text
 */
function bad_request($str = false)
{
    header('Status: 400 Bad Request');
    header('Content-Type: text/plain');
    die($str ? $str : 'bad request');
}

/**
 * Creates a preview content for the given file and mime type.
 * TODO supported types: png, jpg, gif
 * @param string $filename
 * @param string $mime
 * @return string the preview content, false if not supported
 */
function generate_preview_content($filename, $mime)
{
    // load image and get image size
    $func = false;
    switch ($mime) {
        case 'image/png':
            $func = 'imagecreatefrompng';
            break;
        case 'image/gif':
            $func = 'imagecreatefromgif';
            break;
        case 'image/jpeg':
            $func = 'imagecreatefromjpeg';
            break;
        default:
            // mime type not supported
            return false;
    }

    $img = @$func($filename);
    if (!$img)
        return false;
    $width = imagesx( $img );
    $height = imagesy( $img );

    // calculate thumbnail size
    // FIXME this should be configurable
    $thumbWidth = 80;
    $new_width = $thumbWidth;
    $new_height = floor( $height * ( $thumbWidth / $width ) );

    // create a new temporary image
    $tmp_img = imagecreatetruecolor( $new_width, $new_height );

    // copy and resize old image into new image
    imagecopyresized( $tmp_img, $img, 0, 0, 0, 0, $new_width, $new_height, $width, $height );

    // save thumbnail into a file
    ob_start();
    // FIXME saving to png -- what about mime type??
    imagepng($tmp_img, null, 9);
    return ob_get_clean();
}

$mime_types = array(
    'image/png' => 'png',
    'image/jpeg' => 'jpg',
    'image/gif' => 'gif'
);

/**
 * Generates a random file name based on the given mime type.
 * @param string $mime
 * @return string
 */
function generate_filename($mime)
{
    global $mime_types;
    if (isset($mime_types[$mime]))
        return sprintf('att%s.%s', rand_str(6, CHARSBOX_AZN_LOWERCASE), $mime_types[$mime]);
}


?>
