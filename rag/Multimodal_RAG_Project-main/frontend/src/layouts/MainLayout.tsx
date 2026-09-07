import { Outlet } from "react-router-dom";

export default function MainLayout(){
      return (
            <div className="min-h-screen bg-background text-foreground">
                  <Outlet></Outlet>
            </div>
      );
}
