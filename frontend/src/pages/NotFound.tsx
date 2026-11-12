import { Link } from "react-router-dom";
import { Empty } from "../components/ui";

export function NotFound() {
  return (
    <div className="page">
      <Empty title="Page not found" action={<Link className="btn btn-primary" to="/cases">Go to cases</Link>}>
        The address does not match any view in Karsa.
      </Empty>
    </div>
  );
}
