<?php
/**
 * Interface to the attachments table
 * @author Daniele Ricci
 * @version 1.0
 */


class AttachmentsDb extends MessengerDb
{
    /**
     * Retrieves an attachment entry, optionally filtering by user id.
     * @param string $filename
     * @param string $userid
     * @return array
     */
    function get($filename, $userid = false)
    {
        $query = 'SELECT * from attachments WHERE filename = :filename';
        $args = array('filename' => $filename);
        if ($userid) {
            $query .= ' AND userid = :userid';
            $args['userid'] = $userid;
        }

        return $this->get_row($query, $args);
    }

    /**
     * Inserts a new attachments entry.
     * @param $userid
     * @param $filename
     * @param $mime
     * @return bool
     */
    function insert($userid, $filename, $mime)
    {
        return is_int($this->execute_update('INSERT INTO attachments VALUES(?, ?, ?)',
            array($userid, $filename, $mime)));
    }

    /**
     * Deletes an attachment entry.
     * @param string $filename
     * @return bool
     */
    function delete($filename)
    {
        return is_int($this->execute_update('DELETE FROM attachments WHERE filename = ?', array($filename)));
    }
}

?>
