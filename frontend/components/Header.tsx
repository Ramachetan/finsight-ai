import React from 'react';
import { Link } from 'react-router-dom';
import { HandCoins } from 'lucide-react';

const Header: React.FC = () => {


    return (
        <header className="bg-white/80 backdrop-blur-md border-b border-secondary-200 sticky top-0 z-30 shadow-sm">
            <div className="container mx-auto px-4 sm:px-6 lg:px-8">
                <div className="flex items-center justify-between h-16">
                    <div className="flex items-center gap-3">
                        <Link to="/" className="flex items-center gap-3 group">
                            <div className="relative">
                                <HandCoins className="w-10 h-10 text-primary-600 group-hover:text-primary-700 transition-colors" />
                            </div>
                        </Link>
                        <div>
                            <Link to="/" className="block">
                                <h1 className="text-xl font-bold text-primary-900 hover:text-primary-700 transition-colors">
                                    FinSight AI
                                </h1>
                            </Link>
                            <p className="text-xs text-secondary-500">
                                From{' '}
                                <a
                                    href="https://neusis.ai"
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="hover:text-primary-600 hover:underline transition-colors"
                                >
                                    neusis.ai
                                </a>
                            </p>
                        </div>
                    </div>


                </div>
            </div>
        </header>
    );
};

export default Header;
