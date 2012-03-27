<?php

include_once 'version.php';


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


?>
