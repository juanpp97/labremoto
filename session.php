<?php
include('conexion.php'); // Incluye el archivo de conexión
session_start(); // Inicia la sesión


if($_SERVER["REQUEST_METHOD"] == "POST"){
    if(isset($_SESSION["usuario_id"])){
        $usuario_id = $conexion->real_escape_string($_SESSION['usuario_id']);

        // Obtener información del usuario de la base de datos
        $sql = "SELECT clase FROM usuarios WHERE id = '$usuario_id'";
        $result = $conexion->query($sql);


        if ($result && $result->num_rows > 0) {
            $row = $result->fetch_assoc();
            $username = $row["dni"];
        }
        header('Access-Control-Allow-Origin: *');
        http_response_code(200); 
        header('Content-type: application/json');
        echo json_encode( $username );
        exit();
    }
}
header('Access-Control-Allow-Origin: *');
http_response_code(401);
exit();
?>