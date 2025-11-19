// server.js
const express = require('express');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;

// Parsers (built-in)
app.use(express.urlencoded({ extended: true }));
app.use(express.json());

// Static files
app.use(express.static(path.join(__dirname)));

// Home
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'index.html'));
});

/* ------------ AUTH ------------ */
// Login (login.html posts to /login with "identifier" + "password")
app.post('/login', (req, res) => {
  const { identifier, username, password } = req.body;
  const userId = identifier || username || '';
  console.log('Login:', { identifier: userId, password: '[hidden]' });
  // TODO: authenticate userId/password
  res.status(200).send('Login received! (Check your server console)');
});

// Signup (signup form uses these exact fields)
app.post('/signup', (req, res) => {
  const { name, email, phone, password, confirm_password } = req.body;
  console.log('Signup:', { name, email, phone, password: '[hidden]', confirm_password: '[hidden]' });

  if (!name || !email || !password || !confirm_password) {
    return res.status(400).send('Missing required fields.');
  }
  if (password !== confirm_password) {
    return res.status(400).send('Passwords do not match.');
  }
  // TODO: create user
  res.status(200).send('Signup received! (Check your server console)');
});

/* ------------ CONTACT ------------ */
// Contact form (contact.html currently points at form-handler.php)
// Support BOTH /send-message and /form-handler.php so you don’t have to edit HTML.
const handleContact = (req, res) => {
  const { name, email, phone, subject, product, message } = req.body;
  console.log('Contact message:', { name, email, phone, subject, product, message });
  res.status(200).send('Message received! (Check your server console)');
};
app.post('/send-message', handleContact);
app.post('/form-handler.php', handleContact);

/* ------------ FALLBACKS ------------ */
// Optional: nice 404 for unknown routes (static files already handled)
app.use((req, res) => res.status(404).send('Not found'));

/* ------------ START ------------ */
app.listen(PORT, () => {
  console.log(`Server running at http://localhost:${PORT}`);
});
