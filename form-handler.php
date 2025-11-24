<?php
if ($_SERVER["REQUEST_METHOD"] === "POST") {
    $email = filter_var($_POST["email"] ?? "", FILTER_SANITIZE_EMAIL);
    
    if (!$email) {
        die("Invalid email");
    }

    // Your delivery email
    $to = "info@kwetupartners.net";
    $subject = "New Newsletter Subscription";
    $message = "New subscriber: " . $email;
    $headers = "From: noreply@kwetupartners.net\r\n";

    if (mail($to, $subject, $message, $headers)) {
        echo "success";
    } else {
        echo "error";
    }
}
?>
