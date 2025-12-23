import { Routes, Route } from 'react-router-dom';
import Dashboard from './pages/Dashboard.tsx';
import FolderWorkspace from './pages/FolderWorkspace.tsx';
import Preview from './pages/Preview.tsx';
import { ToastContainer } from './components/ui/Toast.tsx';
import Header from './components/Header.tsx';

function App() {
  return (
    <>
      <div className="min-h-screen text-secondary-800">
        <Header />
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/folder/:folderId" element={<FolderWorkspace />} />
          <Route path="/folder/:folderId/preview/:filename" element={<Preview />} />
        </Routes>
      </div>
      <ToastContainer />
    </>
  );
}

export default App;
