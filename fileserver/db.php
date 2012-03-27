<?php
/**
 * Generic interface to messenger database
 * @author Daniele Ricci
 * @version 1.0
 */


include 'messages.php';
include 'usercache.php';
include 'servers.php';
include 'validations.php';
include 'attachments.php';

class MessengerDb
{
    /**
     * PDO database instance
     * @var PDO
     */
    private $db;

    function __construct($db)
    {
        $this->db = $db;
    }

    /**
     * Builds and returns a MessengerDb instance.
     * @param $uri
     * @param $user
     * @param $pass
     * @return MessengerDb
     */
    static function connect($uri = DB_URI, $user = DB_USERNAME, $pass = DB_PASSWORD)
    {
        $db = new PDO($uri, $user, $pass);
        $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_SILENT);
        $db->exec('SET CHARACTER SET utf8');
        return new MessengerDb($db);
    }

    /**
     * Creates a usercache table instance.
     * @return UsercacheDb
     */
    function usercache()
    {
        return new UsercacheDb($this->db);
    }

    /**
     * Creates a messages table instance.
     * @return MessagesDb
     */
    function messages()
    {
        return new MessagesDb($this->db);
    }

    /**
     * Creates a servers table instance.
     * @return ServersDb
     */
    function servers()
    {
        return new ServersDb($this->db);
    }

    /**
     * Creates a validations table instance.
     * @return ValidationsDb
     */
    function validations()
    {
        return new ValidationsDb($this->db);
    }

    /**
     * Creates an attachments table instance.
     * @return AttachmentsDb
     */
    function attachments()
    {
        return new AttachmentsDb($this->db);
    }

    /**
     * Setup a prepared statement.
     * @param string $sql
     * @param array $fields
     * @return PDOStatement
     */
    private function prepare_statement($sql, $fields = null)
    {
        $stm = $this->db->prepare($sql);
        if (is_array($fields)) {
            foreach ($fields as $name => $type) {
                $key = (is_int($name)) ? $name + 1 : $name;

                if (is_array($type))
                    $stm->bindValue($key, $type[0], $type[1]);
                else
                    $stm->bindValue($key, $type);
            }
        }

        return $stm;
    }

    /**
     * Execute a SQL query returning affected rows count.
     * @param string $sql
     * @return int affected rows count, false if error
     */
    function execute_update($sql, $fields = null)
    {
        $stm = $this->prepare_statement($sql, $fields);
        return ($stm->execute()) ? $stm->rowCount() : false;
    }

    /**
     * Execute a SQL query returning a result set.
     * @param string $sql
     * @return PDOStatement
     */
    function execute_query($sql, $fields = null)
    {
        $stm = $this->prepare_statement($sql, $fields);
        if ($stm->execute()) {
            return $stm;
        }
        else {
            $stm->closeCursor();
            return false;
        }
    }

    /**
     * Execute a SELECT query returning the first row.
     * @param $sql
     * @param $fields
     * @return array
     */
    function get_row($sql, $fields = null)
    {
        $stm = $this->execute_query($sql, $fields);

        if ($stm) {
            $rset = $stm->fetch(PDO::FETCH_ASSOC);
            $stm->closeCursor();
            return $rset;
        }
    }

    /**
     * Execute a SELECT query returning all the rows.
     * @param $sql
     * @param $fields
     * @return array
     */
    function get_rows($sql, $fields = null)
    {
        $stm = $this->execute_query($sql, $fields);

        if ($stm) {
            $rset = $stm->fetchAll(PDO::FETCH_ASSOC);
            $stm->closeCursor();
            return $rset;
        }
    }

    /**
     * Execute a SELECT query returning the first column of all rows.
     * @param $sql
     * @param $fields
     * @return array
     */
    function get_rows_list($sql, $fields = null)
    {
        $stm = $this->execute_query($sql, $fields);

        if ($stm) {
            $rset = $stm->fetchAll(PDO::FETCH_COLUMN, 0);
            $stm->closeCursor();
            return $rset;
        }
    }

    /**
     * Unlock all tables.
     * @return bool
     */
    function unlock()
    {
        return is_int($this->execute_update('UNLOCK TABLES'));
    }
}

?>
