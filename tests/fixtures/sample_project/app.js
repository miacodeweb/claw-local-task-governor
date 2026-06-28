function getUser(id) {
  return fetch("/api/users/" + id).then((response) => response.json());
}

console.log(getUser("demo"));
