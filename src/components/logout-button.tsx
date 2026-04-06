export function LogoutButton({ csrfToken }: { csrfToken: string }) {
  return (
    <form action="/auth/logout" method="post">
      <input type="hidden" name="csrfToken" value={csrfToken} />
      <button className="secondary-button" type="submit">Déconnexion</button>
    </form>
  );
}
